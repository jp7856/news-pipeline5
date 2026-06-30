"""
vocab_monitor.py — 어휘 드리프트 모니터링 (방식 3).

게이트 아님 — 차단·재작성 없음. 기록·플래그만.
생성 루프 안에 걸지 말 것: 재작성 트리거로 쓰면 무한루프 위험.

VocabFlag:
  NONE:   C2VA ≤ baseline_pct                              → 정상, 기록 없음
  WEAK:   C2VA > baseline_pct, NOT 단어 0                  → 로그만 (토픽 전문어 가능성)
  STRONG: C2VA > baseline_pct, NOT 단어 1+                 → 사람 검토 목록

baseline_pct는 호출자가 제공 — 이 모듈은 임계값을 확정하지 않는다.
NOT 패턴은 신문별로 호출자가 주입; None이면 TIMES 기본값 적용.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

import cefrpy

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


class VocabFlag(str, Enum):
    NONE   = "NONE"    # C2VA ≤ baseline_pct
    WEAK   = "WEAK"    # C2VA > baseline_pct, NOT 단어 0
    STRONG = "STRONG"  # C2VA > baseline_pct, NOT 단어 1+


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


def check(
    text: str,
    baseline_pct: float,
    not_patterns: dict[str, re.Pattern] | None = None,
) -> MonitorResult:
    """
    text:          기사 본문
    baseline_pct:  섹션 C2VA 기준선 (호출자가 결정 — 이 함수는 수치 확정 없음)
    not_patterns:  신문별 NOT 단어 패턴. None → TIMES 기본값(TIMES_NOT_PATTERNS).

    반환: MonitorResult (flag=NONE/WEAK/STRONG, reason 포함)
    차단·재작성 없음 — 호출자가 flag를 로그/검토목록에 기록하는 것까지만.
    """
    if not_patterns is None:
        not_patterns = TIMES_NOT_PATTERNS

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
    )
