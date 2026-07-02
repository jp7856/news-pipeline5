"""
vocab_monitor.py — 어휘 드리프트 모니터링 (방식 3).

게이트 아님 — 차단·재작성 없음. 기록·플래그만.
생성 루프 안에 걸지 말 것: 재작성 트리거로 쓰면 무한루프 위험.

VocabFlag:
  NONE:   C2VA ≤ baseline_pct, 시드 히트 0                 → 정상, 기록 없음
  WEAK:   C2VA > baseline_pct, NOT 단어 0                  → 로그만 (토픽 전문어 가능성)
  STRONG: C2VA > baseline_pct + NOT 단어 1+, 또는
          시드 히트 1+ (SEED_DRIFT — C2VA와 별개의 독립 축) → 사람 검토 목록

baseline_pct는 호출자가 제공 — 이 모듈은 임계값을 확정하지 않는다.
NOT 패턴은 신문별로 호출자가 주입; None이면 TIMES 기본값 적용.

── analytical_seed 신호 (v1) ────────────────────────────────────────────────
시드 히트 > 0이면 C2VA 판정과 무관하게 STRONG(검토 큐)으로 승격한다 —
"SEED_DRIFT: conduct×1" 형식의 독립 사유. 이것은 임계값이 아니다(0 초과 =
히트 존재 여부일 뿐, 튜닝할 숫자가 없다). 검증셋(C2VA>=4.76% topic 기사
19건)은 전부 시드 히트 0이라 이 규칙으로 걸리지 않음을 실측으로 확인함.
debate/Key Issue 계열은 analytical_seed가 carve-out하므로 승격 대상 아님.
시드는 8개로 고정이며 이 모듈에서 추가·제거하지 않는다(변경은 지침
NOT-examples 갱신 → 수동 반영). 생성·발행 차단 없음 — 검토 큐 신호까지만.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

import cefrpy

from agents.sub_agents import analytical_seed
from agents.sub_agents.vocab_checker import (
    DOMAIN_TERMS,
    NOT_WORDS,
    _SENT_SPLIT,
    _get_candidates,
    get_cefr,
)

_analyzer = cefrpy.CEFRAnalyzer()
_VERB_IDS = frozenset(
    p.value for p in cefrpy.POSTag if p.name in ("VB", "VBD", "VBG", "VBN", "VBP", "VBZ")
)
_ADV_IDS = frozenset(
    p.value for p in cefrpy.POSTag if p.name in ("RB", "RBR", "RBS")
)
_pos_cache: dict[str, str] = {}

# TIMES 기본 NOT 패턴 (vocab_checker.NOT_WORDS 기반, 단어 경계 매칭)
TIMES_NOT_PATTERNS: dict[str, re.Pattern] = {
    w: re.compile(r"\b" + re.escape(w) + r"\b", re.IGNORECASE) for w in NOT_WORDS
}


def _c2_pos_cat(word: str) -> str:
    """C2 단어의 POS 카테고리 반환: '동사' | '부사' | '기타'."""
    if word in _pos_cache:
        return _pos_cache[word]
    cat = "기타"
    for lemma in _get_candidates(word):
        if not _analyzer.is_word_in_database(lemma):
            continue
        found: set[str] = set()
        for pos in cefrpy.POSTag:
            try:
                lv = _analyzer.get_word_pos_level_CEFR(lemma, pos)
                if lv is None or str(lv).strip() not in ("C1", "C2"):
                    continue
                if pos.value in _VERB_IDS:
                    found.add("동사")
                elif pos.value in _ADV_IDS:
                    found.add("부사")
            except Exception:
                pass
        if found:
            cat = "동사" if "동사" in found else "부사"
            break
    _pos_cache[word] = cat
    return cat


# 월간 리뷰 큐(Vocab Review 탭) 상단에 그대로 박는 리뷰 가이드.
# flag 로직 아님 — 리뷰어용 안내 문서 상수.
REVIEW_GUIDE = """\
[Vocab Review 가이드]
flag 의미:
  WEAK   = C2VA > baseline, NOT 단어 0 — 토픽 전문어 가능성 높음. 참고용.
  STRONG = C2VA > baseline + NOT 단어 1+, 또는 SEED_DRIFT(시드 히트 1+) — 사람 판단 필요.
판정 축: C2VA(비율 축, 참고 신호)와 SEED_DRIFT(큐레이션 시드 히트, 독립 축)는 별개.
  SEED_DRIFT: conduct×1 형식 = 어떤 시드 단어가 몇 번 나왔는지.

리뷰 액션 판정 기준:
  정상(오탐)                = 시드/C2VA가 걸렸지만 본문이 타겟 레벨에 적절함.
  드리프트 확인–지침 갱신 필요 = 실제 어휘 드리프트. 수정 위치는 이 스크립트가 아니라
    ① 해당 매체 지침 md의 NOT-examples (agents/guidelines/agent1_4_times.md 류)
    ② vocab_checker.py NOT_WORDS — 반드시 이 순서로 갱신.
    시드는 지침에 먼저 올라간 단어만 승격한다(즉흥 추가 금지).
  드리프트 확인–시드 후보     = 드리프트인데 현 시드가 못 잡은 단어 발견 — 지침 갱신 후보.
  보류                     = 판단 유보. 다음 달 재검토.

"정상(오탐)"이 특정 시드 단어에서 반복되면(예: conduct가 과학 기사에서 계속 오탐):
그 단어의 시드 제외를 검토하되, 이 판단도 지침 갱신을 경유한다.
이 리뷰는 매달 1일 자동 실행된다(Railway cron) — 이번 달 Run Log 행이 없으면 실행이 죽은 것이니 Railway 로그를 확인할 것."""


class VocabFlag(str, Enum):
    NONE   = "NONE"    # C2VA ≤ baseline_pct, 시드 히트 0
    WEAK   = "WEAK"    # C2VA > baseline_pct, NOT 단어 0
    STRONG = "STRONG"  # C2VA > baseline_pct + NOT 단어 1+, 또는 시드 히트 1+ (SEED_DRIFT)


@dataclass
class MonitorResult:
    c2va_pct:      float
    c2va_count:    int
    total_words:   int
    not_word_hits: dict[str, int] = field(default_factory=dict)
    c2va_words:    list[str]      = field(default_factory=list)
    flag:          VocabFlag      = VocabFlag.NONE
    flag_reason:   str            = ""
    baseline_pct:  float          = 0.0
    above_baseline: bool          = False
    # ── analytical_seed 신호 (v1) — flag 결정에 관여 안 함, 부가 정보만 ──────
    seed_hits_per_100:  float           = 0.0
    seed_hit_count:     int             = 0
    seed_matched_words: dict[str, int]  = field(default_factory=dict)
    seed_carved_out:    bool            = False
    seed_skipped_reason: str            = ""


def check(
    text: str,
    baseline_pct: float,
    not_patterns: dict[str, re.Pattern] | None = None,
    section: str = "",
    level_key: str = "TIMES_L2",
) -> MonitorResult:
    """
    text:          기사 본문
    baseline_pct:  섹션 C2VA 기준선 (호출자가 결정 — 이 함수는 수치 확정 없음)
    not_patterns:  신문별 NOT 단어 패턴. None → TIMES 기본값(TIMES_NOT_PATTERNS).
    section:       기사 섹션명 — analytical_seed의 debate/Key Issue carve-out 판정에만 사용.
    level_key:     article_classifier.BRIEF_THRESHOLD 키 (예: 'KINDER_L2') —
                   analytical_seed의 BRIEF/DIALOGUE carve-out 임계값에만 사용.
                   미지정 시 TIMES_L2 기준이라 짧은 매체(KINDER 등)는 전부
                   BRIEF로 carve-out되므로 호출자가 매체에 맞게 넘겨야 한다.

    반환: MonitorResult (flag=NONE/WEAK/STRONG, reason 포함)
    차단·재작성 없음 — 호출자가 flag를 로그/검토목록에 기록하는 것까지만.
    """
    if not_patterns is None:
        not_patterns = TIMES_NOT_PATTERNS

    seed_result = analytical_seed.measure(text, section=section, level_key=level_key)

    # NOT 단어: 원문 패턴 매칭 (단어 경계, 대소문자 무시)
    not_hits: dict[str, int] = {
        w: cnt for w, p in not_patterns.items() if (cnt := len(p.findall(text))) > 0
    }

    # C2VA: dedup 스캔
    seen: set[str] = set()
    total = c2va = 0
    c2va_words: list[str] = []

    for sent in _SENT_SPLIT.split(text.strip()):
        for i, raw in enumerate(re.findall(r"[A-Za-z]+", sent)):
            if raw[0].isupper() and i > 0:
                continue
            w = raw.lower()
            if len(w) <= 2 or w in DOMAIN_TERMS or w in seen:
                continue
            seen.add(w)
            lv = get_cefr(w)
            if lv is None:
                continue
            total += 1
            if lv == "C2" and _c2_pos_cat(w) in ("동사", "부사"):
                c2va += 1
                c2va_words.append(w)

    c2va_pct = round(c2va / total * 100, 2) if total else 0.0
    above = c2va_pct > baseline_pct

    if not above:
        flag = VocabFlag.NONE
        reason = f"C2VA {c2va_pct:.2f}% ≤ baseline {baseline_pct:.2f}%"
    elif not not_hits:
        flag = VocabFlag.WEAK
        reason = f"C2VA {c2va_pct:.2f}% > {baseline_pct:.2f}%, NOT 단어 없음"
    else:
        flag = VocabFlag.STRONG
        words_str = ", ".join(f"{w}×{n}" for w, n in not_hits.items())
        reason = f"C2VA {c2va_pct:.2f}% > {baseline_pct:.2f}%, NOT: {words_str}"

    # 시드 히트는 C2VA와 별개의 독립 큐 포함 사유 — 히트 1+면 STRONG으로 승격.
    # 임계값 아님: 0 초과 = 히트 존재 여부일 뿐, 튜닝할 숫자가 없다.
    if seed_result.carved_out:
        reason += f" | seed: carve-out ({seed_result.skipped_reason})"
    elif seed_result.hit_count:
        seed_words_str = ", ".join(f"{w}×{n}" for w, n in seed_result.matched_words.items())
        flag = VocabFlag.STRONG
        reason += f" | SEED_DRIFT: {seed_words_str} ({seed_result.hits_per_100}/100)"

    return MonitorResult(
        c2va_pct=c2va_pct,
        c2va_count=c2va,
        total_words=total,
        not_word_hits=not_hits,
        c2va_words=c2va_words,
        flag=flag,
        flag_reason=reason,
        baseline_pct=baseline_pct,
        above_baseline=above,
        seed_hits_per_100=seed_result.hits_per_100,
        seed_hit_count=seed_result.hit_count,
        seed_matched_words=seed_result.matched_words,
        seed_carved_out=seed_result.carved_out,
        seed_skipped_reason=seed_result.skipped_reason,
    )
