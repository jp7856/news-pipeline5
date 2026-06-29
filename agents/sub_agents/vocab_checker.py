"""
vocab_checker.py — C1+ 어휘 비율 측정기 (기록·경고용, 차단 없음)

Words-CEFR-Dataset (MIT, cefrpy) 기반.
레마타이제이션 적용, 고유명사(문장 중간 대문자 시작) 및 1~2자 단어 제외.
도메인 전문어(guidelines B2 OK 목록)는 비율 분모에서 제외.
임계값·차단 로직 없음 — 측정값 반환만.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import cefrpy

_analyzer = cefrpy.CEFRAnalyzer()
_CEFR_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2"]

# ── Domain whitelist ──────────────────────────────────────────────────────────
# guidelines가 B2에서 OK라고 명시한 전문어 + 교육신문 빈출 전문어.
# 이 단어들은 비율 분모(total_words)에서 제외해 C1+ 오탐을 방지한다.
DOMAIN_TERMS: frozenset[str] = frozenset({
    # guidelines 명시
    "gdp", "legislation", "surveillance",
    # 교육신문 빈출 — 토픽 종속 전문어, 문체 난이도 반영 안 함
    "parliament", "legislature", "congress", "senate", "referendum", "sanctions",
    "inflation", "recession", "deficit", "subsidies", "tariffs",
    "emissions", "biodiversity", "semiconductor", "algorithm",
    "metabolism", "antibiotics", "vaccination", "pandemic",
    "constitution", "sovereignty", "jurisdiction", "diplomatic", "diplomacy",
})

# ── guidelines NOT 단어 (8개) ─────────────────────────────────────────────────
# L1 금지 5개: proponents, deterring/deterring→deter, incorporating, measurable, advocates
# L2/L3 금지 3개: proliferation, contend, conducted
NOT_WORDS: tuple[str, ...] = (
    "proponents", "deterring", "incorporating", "measurable",
    "proliferation", "advocates", "contend", "conducted",
)
_NOT_PATTERNS: dict[str, re.Pattern] = {
    w: re.compile(r'\b' + re.escape(w) + r'\b', re.IGNORECASE)
    for w in NOT_WORDS
}

# ── 내부 CEFR 레벨 캐시 ───────────────────────────────────────────────────────
_cefr_cache: dict[str, str | None] = {}


def _get_candidates(word: str) -> list[str]:
    """기본형 후보 목록 반환 (우선순위 순)."""
    w = word.lower()
    cands = [w]

    # -ing 형태
    if w.endswith("ing") and len(w) > 5:
        base = w[:-3]
        cands.append(base + "e")       # incorporating → incorporate
        cands.append(base)
        if len(base) >= 2 and base[-1] == base[-2]:   # deterring → deter
            cands.append(base[:-1])

    # -ed 형태
    if w.endswith("ed") and len(w) > 4:
        base = w[:-2]
        cands.append(base)             # conducted → conduct
        cands.append(base + "e")       # used → use
        if len(base) >= 2 and base[-1] == base[-2]:
            cands.append(base[:-1])

    # -s / -es / -ies
    if w.endswith("ies") and len(w) > 4:
        cands.append(w[:-3] + "y")
    elif w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        cands.append(w[:-1])           # proponents → proponent

    return cands


def _lookup(lemma: str) -> str | None:
    """cefrpy에서 단어의 가장 낮은(=기본) CEFR 레벨 반환."""
    if not _analyzer.is_word_in_database(lemma):
        return None
    levels: list[str] = []
    for pos in cefrpy.POSTag:
        try:
            lv = _analyzer.get_word_pos_level_CEFR(lemma, pos)
            if lv is not None:
                s = str(lv).strip()
                if s and s != "None" and s in _CEFR_ORDER:
                    levels.append(s)
        except Exception:
            pass
    if not levels:
        return None
    return min(levels, key=lambda x: _CEFR_ORDER.index(x))


def get_cefr(word: str) -> str | None:
    """단어의 CEFR 레벨 반환. lemmatize 적용, 캐시 사용. 미수록이면 None."""
    w = word.lower()
    if w in _cefr_cache:
        return _cefr_cache[w]
    for lemma in _get_candidates(w):
        lv = _lookup(lemma)
        if lv is not None:
            _cefr_cache[w] = lv
            return lv
    _cefr_cache[w] = None
    return None


@dataclass
class VocabResult:
    total_words: int            # 분석 대상 단어 수 (고유명사·도메인 제외 후 DB 수록 단어)
    c1_count: int
    c2_count: int
    c1plus_ratio: float         # (c1+c2) / total_words; total_words==0이면 0.0
    not_word_hits: dict[str, int] = field(default_factory=dict)  # NOT 단어 → 출현 횟수
    domain_excluded: int = 0    # 도메인 화이트리스트로 분모 제외된 단어 수
    proper_excluded: int = 0    # 고유명사로 제외된 단어 수

    @property
    def c1plus_pct(self) -> float:
        return round(self.c1plus_ratio * 100, 1)


_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+')
_TOKEN = re.compile(r'[A-Za-z]+')


def measure(text: str, dedup_types: bool = False) -> VocabResult:
    """기사 본문 C1+ 어휘 비율 측정. 차단 없음 — 측정값만 반환.

    dedup_types=True: 동일 소문자 토큰은 기사 내 1회만 집계.
    토픽 전문어(cicada, pastry 등) 반복으로 인한 비율 부풀림을 제거한다.
    분자(C1/C2)와 분모(total) 모두 동일 규칙 적용.
    """

    # NOT 단어 raw 카운트 (lemmatize 없이 원문 패턴 매칭)
    not_hits = {
        w: cnt
        for w, p in _NOT_PATTERNS.items()
        if (cnt := len(p.findall(text))) > 0
    }

    total = 0
    c1 = 0
    c2 = 0
    domain_excl = 0
    proper_excl = 0
    seen: set[str] = set()

    for sent in _SENT_SPLIT.split(text.strip()):
        tokens = _TOKEN.findall(sent)
        for i, raw in enumerate(tokens):

            # 고유명사: 문장 중간(i > 0)에서 대문자로 시작하는 단어
            if raw[0].isupper() and i > 0:
                proper_excl += 1
                continue

            w = raw.lower()

            # 1~2자 스킵
            if len(w) <= 2:
                continue

            # 도메인 전문어 제외 (분모에서 제거)
            if w in DOMAIN_TERMS:
                domain_excl += 1
                continue

            # dedup: 이미 집계한 토큰이면 스킵 (분자·분모 모두)
            if dedup_types:
                if w in seen:
                    continue
                seen.add(w)

            lv = get_cefr(w)
            if lv is None:
                continue          # 미수록 단어는 분모에서도 제외

            total += 1
            if lv == "C1":
                c1 += 1
            elif lv == "C2":
                c2 += 1

    ratio = (c1 + c2) / total if total > 0 else 0.0
    return VocabResult(
        total_words=total,
        c1_count=c1,
        c2_count=c2,
        c1plus_ratio=ratio,
        not_word_hits=not_hits,
        domain_excluded=domain_excl,
        proper_excluded=proper_excl,
    )
