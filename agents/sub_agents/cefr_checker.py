"""
cefr_checker.py — 레벨별 난이도 검증 (API 호출 없음, 순수 계산)

기존 cefr_loop.py 초안에서 검증 부분만 분리 + 실측 보정:
- 상한뿐 아니라 하한(avg_sentence_len)도 검사 → 목표보다 "너무 쉬운" 기사도 거름
- FK 상한을 NE Times 실측에 맞게 조정 (표의 일반 영어 기준값은 너무 낮았음)
- 위반 문장을 정확히 추출해 재작성 피드백으로 넘김
- 고유명사 제외 FK 보정은 실측 결과 효과 미미(+0.1~1.1)하여 미적용

sub_agents/ 폴더에 두고 reviewer.py / content_producer.py 의 검증 루프에서 호출.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

try:
    import textstat
    _HAS_TEXTSTAT = True
except ImportError:
    _HAS_TEXTSTAT = False


# --------------------------------------------------------------------------
# 레벨 스펙: 범위(min~max) + 절/FK 상한
#   avg_min/avg_max : 평균 문장 길이 허용 범위 (하한 = 너무 쉬움 차단)
#   max_sentence_len: 최장 문장 단어 수 상한
#   max_clauses     : 한 문장 최대 절 개수
#   fk_max          : Flesch-Kincaid 학년 상한 (실측 보정값)
#
# 5개 지표 전수 보정 — basic.xlsx 전수 실측 (tests/measure_all_levels.py + diagnose_cefr.py)
#   avg_min = p10, avg_max/maxlen/clauses/fk_max = p90
#   레벨키       n   avg_min  avg_max  maxlen  clauses  fk_max
#   KINDER_L1   32     4.0     6.5     13       2       3.5
#   KINDER_L2   16     5.0     9.5     23       2       6.0
#   KIDS_L1     16     7.0    11.0     19       3       7.5
#   KIDS_L2     40     7.0    12.0     25       3       9.0
#   KIDS_L3     16     7.5    12.5     25       3       8.5
#   JUNIOR_L1   40    10.5    14.5     25       4       9.0  ← NE You 제외 기준 (비-NE p10)
#   JUNIOR_L2   24    10.5    16.5     34       4      10.5  ← 경계 샘플(10.8~12.0) 99건 수용
#   JUNIOR_L3   16    11.5    17.5     27       4      11.5  ← World Tour 경계 기준 (p10)
#   JUNIORM_L1  69     9.4    17.0     31       4      10.0  ← p10 기준 (문장 짧은 게 정상, avg로 거의 안 거름)
#   JUNIORM_L2  19    10.1    15.0     33       4      10.0  ← p10 기준
#   TIMES_L1    56    10.5    19.0     32       4      12.5  ← 10.5: articles.xlsx 실측 조정 (avg 9~10은 JUNIOR급)
#   TIMES_L2    48    13.5    19.5     31       5      13.0  ← 14.5→13.5 (articles.xlsx 경계 샘플 검토)
#   TIMES_L3    20    15.5    19.0     48       6      14.0
# --------------------------------------------------------------------------
@dataclass
class LevelSpec:
    name: str
    avg_min: float
    avg_max: float
    max_sentence_len: int
    max_clauses: int
    fk_max: float


LEVELS: dict[str, LevelSpec] = {
    # 매체     레벨   avg_min avg_max maxlen clause fk_max
    #          avg_min = basic.xlsx p10  (하한: 이보다 짧으면 "너무 쉬움")
    #          avg_max/maxlen/clauses/fk_max = basic.xlsx p90  (상한)
    "KINDER_L1": LevelSpec("KINDER L1",  4.0,  6.5, 13, 2,  3.5),
    "KINDER_L2": LevelSpec("KINDER L2",  5.0,  9.5, 23, 2,  6.0),
    "KIDS_L1":   LevelSpec("KIDS L1",    7.0, 11.0, 19, 3,  7.5),
    "KIDS_L2":   LevelSpec("KIDS L2",    7.0, 12.0, 25, 3,  9.0),
    "KIDS_L3":   LevelSpec("KIDS L3",    7.5, 12.5, 25, 3,  8.5),
    "JUNIOR_L1": LevelSpec("JUNIOR L1", 10.5, 14.5, 25, 4,  9.0),
    "JUNIOR_L2": LevelSpec("JUNIOR L2", 10.5, 16.5, 34, 4, 10.5),
    "JUNIOR_L3": LevelSpec("JUNIOR L3", 11.5, 17.5, 27, 4, 11.5),
    "JUNIORM_L1":LevelSpec("JUNIOR M L1", 9.4,17.0, 31, 4, 10.0),
    "JUNIORM_L2":LevelSpec("JUNIOR M L2",10.1,15.0, 33, 4, 10.0),
    "TIMES_L1":  LevelSpec("TIMES L1",  10.5, 19.0, 32, 4, 12.5),
    "TIMES_L2":  LevelSpec("TIMES L2",  13.5, 19.5, 31, 5, 13.0),  # ← 14.5→13.5: 경계 샘플 확인 후 조정 (L1 중앙값 12.5 이상만 통과)
    "TIMES_L3":  LevelSpec("TIMES L3",  15.5, 19.0, 48, 6, 14.0),
}


@dataclass
class CefrResult:
    passed: bool
    level: str
    avg_sentence_len: float
    max_sentence_len: int
    max_clauses: int
    fk_grade: float
    sentence_count: int
    violations: list[str] = field(default_factory=list)
    too_long_sentences: list[str] = field(default_factory=list)   # 길이/절 위반 문장
    too_easy: bool = False                                          # 하한 미달 여부


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p.strip()]


def _count_clauses(sentence: str) -> int:
    markers = re.findall(
        r"\b(and|but|or|because|although|though|which|who|that|when|while|if|since)\b",
        sentence, flags=re.IGNORECASE,
    )
    return 1 + len(markers) + sentence.count(";") + sentence.count("—")


def _syllables(word: str) -> int:
    word = word.lower()
    groups = re.findall(r"[aeiouy]+", word)
    n = len(groups)
    if word.endswith("e") and n > 1:
        n -= 1
    return max(1, n)


def _fk_grade(text: str) -> float:
    if _HAS_TEXTSTAT:
        return round(textstat.flesch_kincaid_grade(text), 1)
    words = re.findall(r"[A-Za-z]+", text)
    sents = _split_sentences(text) or [text]
    syll = sum(_syllables(w) for w in words) or 1
    w = len(words) or 1
    return round(0.39 * (w / len(sents)) + 11.8 * (syll / w) - 15.59, 1)


def validate(text: str, level: str) -> CefrResult:
    """
    text  : 검사할 기사 본문
    level : LEVELS 의 키 (예: 'TIMES_L2'). 기사가 어느 레벨을 목표로
            생성됐는지 반드시 함께 넘겨야 정확한 판정이 됨.
    """
    spec = LEVELS[level]
    sentences = _split_sentences(text)
    word_counts = [len(re.findall(r"[A-Za-z']+", s)) for s in sentences]
    clause_counts = [_count_clauses(s) for s in sentences]

    avg_len = round(sum(word_counts) / len(word_counts), 1) if word_counts else 0.0
    max_len = max(word_counts) if word_counts else 0
    max_cl = max(clause_counts) if clause_counts else 0
    fk = _fk_grade(text)

    violations: list[str] = []
    too_long: list[str] = []
    too_easy = False

    # ── 하드 게이트: FK 상한 + avg 하한 ─────────────────────────────────
    if fk > spec.fk_max:
        violations.append(f"FK {fk}학년 (상한 {spec.fk_max})")
    if avg_len < spec.avg_min:
        too_easy = True
        violations.append(
            f"평균 문장 길이 {avg_len} (하한 {spec.avg_min} 미달 → 목표보다 쉬움)"
        )

    # ── 소프트 힌트: 재작성 피드백용, 통과/실패에 영향 없음 ─────────────
    if max_len > spec.max_sentence_len:
        violations.append(f"최장 문장 {max_len}단어 (참고 상한 {spec.max_sentence_len})")
    if max_cl > spec.max_clauses:
        violations.append(f"한 문장 절 {max_cl}개 (참고 상한 {spec.max_clauses})")
    if avg_len > spec.avg_max:
        violations.append(f"평균 문장 길이 {avg_len} (참고 상한 {spec.avg_max} 초과)")

    # 재작성 타겟 문장: 길이/절 참고 상한 넘긴 문장
    for s, wc, cc in zip(sentences, word_counts, clause_counts):
        if wc > spec.max_sentence_len or cc > spec.max_clauses:
            too_long.append(s)

    return CefrResult(
        passed=(fk <= spec.fk_max and avg_len >= spec.avg_min),
        level=spec.name,
        avg_sentence_len=avg_len,
        max_sentence_len=max_len,
        max_clauses=max_cl,
        fk_grade=fk,
        sentence_count=len(sentences),
        violations=violations,
        too_long_sentences=too_long,
        too_easy=too_easy,
    )


def build_feedback(result: CefrResult) -> str:
    """검증 실패 시 재작성 프롬프트에 넣을 구체적 피드백 생성."""
    lines = [f"The draft does not match the {result.level} level. Fix ONLY these:"]
    lines += [f"- {v}" for v in result.violations]
    if result.too_long_sentences:
        lines.append("Split these sentences (too long or too many clauses):")
        lines += [f'  · "{s}"' for s in result.too_long_sentences[:5]]
    if result.too_easy:
        lines.append(
            "The writing is TOO SIMPLE for this level. Combine short sentences "
            "using relative or subordinate clauses to raise the average length."
        )
    lines.append("Keep the meaning and the rest of the text unchanged.")
    return "\n".join(lines)


if __name__ == "__main__":
    samples = [
        ("해수욕장", "TIMES_L1", "The beach season in Korea is just around the corner. This year, beaches will open later than last year, but they will stay open longer. Haeundae and Songjeong beaches in Busan will open on June 26th. Haeundae will remain open until September 15th, while Songjeong will close on August 31st. Beaches in Jeju Island will open on June 24th and remain open until September 6th. This period is six days longer than last year, and all beaches will now share the same schedule, from 10 a.m. to 7 p.m. Nationwide, most beaches will open in late June or early July and close by late August. Authorities are preparing stronger safety measures to protect visitors this year, including more lifeguards, jellyfish monitoring, and rip current checks."),
    ]
    for name, level, text in samples:
        r = validate(text, level)
        print(f"[{name}] 목표={r.level} passed={r.passed}")
        print(f"  avg={r.avg_sentence_len} max_len={r.max_sentence_len} clauses={r.max_clauses} fk={r.fk_grade}")
        for v in r.violations:
            print(f"  - {v}")
        if not r.passed:
            print("  --- 재작성 피드백 ---")
            print("  " + build_feedback(r).replace("\n", "\n  "))
