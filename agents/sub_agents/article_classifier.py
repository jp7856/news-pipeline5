"""
article_classifier.py — 기사 유형 판별 (BRIEF / DIALOGUE / ARTICLE)

CEFR 난이도 게이트 앞단에서 호출. 유형에 따라 게이트를 건너뛰거나 통과시킨다.
  BRIEF    : 레벨별 단어수 임계값 미만 → CEFR SKIP
  DIALOGUE : 화자줄("이름: 발화내용") 3회 이상 → CEFR SKIP
  ARTICLE  : 나머지 → CEFR 게이트로 진행
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class ArticleType(Enum):
    ARTICLE  = "ARTICLE"
    BRIEF    = "BRIEF"
    DIALOGUE = "DIALOGUE"


# ── 레벨별 단신 임계값 ────────────────────────────────────────────────────
# 정규 기사 최솟값(SUBLEVEL_CONFIG 기준)에서 여유를 준 값.
# "100단어짜리 TIMES 기사"는 단신이고, "179단어 JUNIOR급 쉬운 기사"는 ARTICLE.
BRIEF_THRESHOLD: dict[str, int] = {
    "KINDER_L1":  30,   # 기사 자체 40~55단어
    "KINDER_L2":  40,   # 기사 자체 55~90단어
    "KIDS_L1":    50,   # 정규 최소 60단어
    "KIDS_L2":    50,
    "KIDS_L3":    50,
    "JUNIOR_L1":  80,   # 정규 최소 115단어
    "JUNIOR_L2":  80,
    "JUNIOR_L3":  80,
    "JUNIORM_L1": 100,  # 정규 최소 150단어
    "JUNIORM_L2": 100,
    "TIMES_L1":   100,  # 정규 최소 110단어
    "TIMES_L2":   100,
    "TIMES_L3":   100,
}

# ── 논리/구조 마커 — 화자줄로 치지 않음 ──────────────────────────────────
# 토론 에세이(Debate 섹션 등)에서 "Premise: If A then B" 같은 줄이
# 화자줄로 오인되는 false positive를 막기 위한 제외 목록.
STRUCTURAL_MARKERS: frozenset[str] = frozenset({
    # 논리학·논증
    "Premise", "Conclusion", "Therefore", "Argument", "Counter",
    "Evidence", "Reason", "Fallacy", "Case",
    # 글쓰기 구조
    "Example", "Note", "Warning", "Result", "Summary",
    "Definition", "Rule", "Type", "Method", "Step", "Point",
    # 토론 포맷
    "Fact", "Opinion", "Pro", "Con", "Question", "Answer", "Response",
})

DIALOGUE_THRESHOLD = 3     # 화자줄이 이 수 이상이면 DIALOGUE
_SPEAKER_CONTENT_MIN = 5   # 콜론 뒤 내용 단어수 최소값 (프로필 필드 제외용)

_DIALOGUE_PREFIX = re.compile(
    r"^\s*([A-Z][a-z]{1,19}(?:\s[A-Z][a-z]{1,19})?):\s+(.*)"
)


def _is_speaker_line(line: str) -> tuple[bool, str]:
    """(화자줄 여부, 감지된 줄 원문) 반환."""
    m = _DIALOGUE_PREFIX.match(line)
    if not m:
        return False, ""
    name_part   = m.group(1).strip()
    content     = m.group(2)
    first_word  = name_part.split()[0]

    # 구조 마커 제외
    if first_word in STRUCTURAL_MARKERS:
        return False, ""

    # 발화 내용 최소 단어수 (프로필 필드 "Height: 185 cm" 등 제외)
    if len(re.findall(r"\w+", content)) < _SPEAKER_CONTENT_MIN:
        return False, ""

    return True, line.strip()


@dataclass
class ClassificationResult:
    article_type: ArticleType
    word_count: int
    dialogue_line_count: int = 0
    dialogue_line_ratio: float = 0.0   # 화자줄 / 전체 비공백 줄
                                        # 순수 대화체: 0.5+ / 논리에세이 예시 삽입: 0.1~0.3
    dialogue_examples: list[str] = field(default_factory=list)
    skip_cefr: bool = False
    brief_threshold: int = 0

    def build_log(self, agent_label: str) -> str:
        """self._log()에 넘길 메시지 반환. ARTICLE이면 빈 문자열."""
        if self.article_type == ArticleType.BRIEF:
            return (
                f"[{agent_label}] 유형=BRIEF — {self.word_count}단어 "
                f"(임계값 {self.brief_threshold} 미만) "
                f"→ CEFR 난이도 게이트 SKIP → 별도 검증 대상 플래그"
            )
        if self.article_type == ArticleType.DIALOGUE:
            examples = " / ".join(
                f'"{e[:50]}"' for e in self.dialogue_examples[:2]
            )
            return (
                f"[{agent_label}] 유형=DIALOGUE — 화자 패턴 {self.dialogue_line_count}건 "
                f"(비율 {self.dialogue_line_ratio:.0%}, {examples}) "
                f"→ CEFR 난이도 게이트 SKIP → 별도 검증 대상 플래그"
            )
        return ""


def classify(text: str, level_key: str) -> ClassificationResult:
    """기사 유형 판별.

    text      : 기사 본문
    level_key : BRIEF_THRESHOLD 키 (예: 'TIMES_L1')
    """
    wc        = len(re.findall(r"[A-Za-z']+", text))
    threshold = BRIEF_THRESHOLD.get(level_key, 100)

    # ── 1. 단신 판정 ───────────────────────────────────────────────────────
    if wc < threshold:
        return ClassificationResult(
            article_type=ArticleType.BRIEF,
            word_count=wc,
            skip_cefr=True,
            brief_threshold=threshold,
        )

    # ── 2. 대화체 판정 ─────────────────────────────────────────────────────
    lines = text.splitlines()
    non_empty = sum(1 for l in lines if l.strip())
    speaker_lines: list[str] = []
    for line in lines:
        ok, matched = _is_speaker_line(line)
        if ok:
            speaker_lines.append(matched)

    ratio = len(speaker_lines) / non_empty if non_empty > 0 else 0.0

    if len(speaker_lines) >= DIALOGUE_THRESHOLD:
        return ClassificationResult(
            article_type=ArticleType.DIALOGUE,
            word_count=wc,
            dialogue_line_count=len(speaker_lines),
            dialogue_line_ratio=ratio,
            dialogue_examples=speaker_lines[:2],
            skip_cefr=True,
        )

    # ── 3. 일반 기사 ───────────────────────────────────────────────────────
    return ClassificationResult(
        article_type=ArticleType.ARTICLE,
        word_count=wc,
        dialogue_line_count=len(speaker_lines),  # 0 or 1~2 (임계값 미달)
        dialogue_line_ratio=ratio,
        skip_cefr=False,
    )
