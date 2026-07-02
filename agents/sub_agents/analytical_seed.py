"""
analytical_seed.py — 어휘 드리프트 탐지용 analytical seed 신호 (v1)

배경: CEFR 검증(평균 문장 길이·Flesch-Kincaid)은 문장 "형태"만 본다. 문장은
짧아도 논증 어휘(analytical vocabulary)가 끼면 실제 난이도가 타겟 레벨보다
높아지는 글(CCTV류)을 못 잡는다.

이미 죽은 접근(반복 금지): fk_min 하한, C1+ ratio, C2VA ratio, doc_freq,
word frequency, NOT_WORDS를 게이트로 쓰는 것 — 전부 "통계 집합(레벨 X 이상
전부·빈도 하위 N% 등) 위의 비율"이었다. topic-specific 어휘(broods, decompose,
pastry, verdant)와 분석 어휘(proliferation, contend, conducted)의 구분은
통계적 성질이 아니라 의미론적이라 어떤 분포 지표로도 안 갈린다.

이 모듈의 접근: "직접 큐레이션한 시드 단어의 형태 변화만 카운트."
시드에 없는 단어는 절대 안 세므로, topic 오염이 구조적으로 불가능하다.

⚠️ hits_per_100도 ratio다. 하지만 "의미론적 집합(사람이 고른 분석 어휘
리스트) 위의 비율"이며, 죽은 접근들의 "통계 집합 위의 비율"과는 다르다 —
전자는 무엇을 셀지 사람이 미리 결정하고, 후자는 분포 성질로 자동 결정한다.
이 구분이 흐려지면 사문화된 ratio 튜닝으로 되돌아간다.

게이트 아님 — 차단·재작성 없음. vocab_monitor.py 월간 리뷰 큐에 담을 신호.
생성 루프 안에 걸지 말 것.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from agents.sub_agents.vocab_checker import NOT_WORDS, _get_candidates, _SENT_SPLIT
from agents.sub_agents.article_classifier import classify, ArticleType

# ── 시드 ────────────────────────────────────────────────────────────────────
# writer.py가 지침(agents/guidelines/agent1_4_times.md의 "Vocabulary guardrails"
# NOT-examples)에서 뽑아 Writer 프롬프트에 주입하는 것과 같은 어휘.
# vocab_checker.py가 이미 이를 씨앗으로 큐레이션해뒀다(TIMES L1 5개 + L2/L3 3개).
# 새로 만들지 않고 그대로 재사용한다.
SEED_WORDS: tuple[str, ...] = NOT_WORDS

# 시드 각 단어의 형태 변화 후보를 미리 전개해 하나의 집합으로 합친다.
# 매칭은 "기사 토큰의 후보 집합 ∩ 이 집합"으로만 판정한다 —
# 임베딩/유의어 확장 없음(argue/assert는 시드에 없으면 안 잡힘).
_SEED_LEMMA_SET: frozenset[str] = frozenset(
    cand for w in SEED_WORDS for cand in _get_candidates(w)
) | frozenset(SEED_WORDS)

# ── debate/Key Issue carve-out ───────────────────────────────────────────────
# contend/proponents 등 분석 어휘는 찬반토론(Debate)·Key Issue 포맷에서는
# 정상적인 토론 어휘라 false-positive로 튄다. writer.py가 JUNIOR M 지침에서
# "Key Issue & Debating"을 비산문(생성 대상 아님) 포맷으로 다루는 것과 같은 근거.
DEBATE_LIKE_SECTIONS: frozenset[str] = frozenset({"debate", "debating", "key issue"})

_TOKEN = re.compile(r"[A-Za-z']+")


@dataclass
class SeedResult:
    hits_per_100: float                              # 시드 히트 수 / 100토큰
    hit_count: int
    total_tokens: int
    matched_words: dict[str, int] = field(default_factory=dict)  # 표면형 -> 횟수
    carved_out: bool = False                          # debate/Key Issue 등 제외 여부
    skipped_reason: str = ""


def measure(text: str, section: str = "", level_key: str = "TIMES_L2") -> SeedResult:
    """기사 본문의 시드(분석 어휘) 히트를 100토큰당으로 정규화해 반환한다.

    - section이 debate/Key Issue 계열이면 측정하지 않는다(위 근거).
    - article_classifier가 ARTICLE이 아니면(BRIEF/DIALOGUE) 측정하지 않는다.
    - 차단·재작성 없음 — 측정값만 반환. 플래그 여부는 호출자(vocab_monitor.py)가 정한다.
    """
    if section.strip().lower() in DEBATE_LIKE_SECTIONS:
        return SeedResult(0.0, 0, 0, carved_out=True, skipped_reason=f"debate-like section: {section!r}")

    cls = classify(text, level_key)
    if cls.article_type != ArticleType.ARTICLE:
        return SeedResult(
            0.0, 0, 0, carved_out=True,
            skipped_reason=f"article_type={cls.article_type.value}",
        )

    matched: dict[str, int] = {}
    total = 0
    for sent in _SENT_SPLIT.split(text.strip()):
        for i, raw in enumerate(_TOKEN.findall(sent)):
            if raw[0].isupper() and i > 0:
                continue  # 문장 중간 고유명사 제외 — vocab_checker.py와 동일 규칙
            w = raw.lower()
            if len(w) <= 2:
                continue
            total += 1
            cands = set(_get_candidates(w))
            cands.add(w)
            if cands & _SEED_LEMMA_SET:
                matched[w] = matched.get(w, 0) + 1

    hit_count = sum(matched.values())
    per100 = round(hit_count / total * 100, 3) if total else 0.0
    return SeedResult(per100, hit_count, total, matched)
