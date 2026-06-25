"""
article_classifier.py — 기사 유형 판별 (BRIEF / DIALOGUE / ARTICLE)

CEFR 난이도 게이트 앞단에서 호출. 유형에 따라 게이트를 건너뛰거나 통과시킨다.
  BRIEF    : 레벨별 단어수 임계값 미만 → CEFR SKIP
  DIALOGUE : 화자줄 3회 이상 → CEFR SKIP. 두 가지 패턴을 감지:
               (a) 콜론 포맷   "Sue: I think..."  (같은 줄에 이름+콜론+발화)
               (b) 단독줄 포맷 "Henry\\n발화내용"  (이름만 한 줄, 다음 줄에 발화)
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
_SPEAKER_CONTENT_MIN = 5   # 발화 내용 최소 단어수

# ── 패턴 (a): 콜론 포맷 "Sue: I think..." ────────────────────────────────
_DIALOGUE_PREFIX = re.compile(
    r"^\s*([A-Z][a-z]{1,19}(?:\s[A-Z][a-z]{1,19})?):\s+(.*)"
)

# ── 패턴 (b): 단독줄 포맷 "Henry\n발화내용" ──────────────────────────────
# 콜론 없이 이름만 한 줄 전체를 차지하고 다음 줄에 발화가 오는 형태.
# (JUNIOR_L3 Debate 등)
_HEADING_SPEAKER = re.compile(r"^\s*([A-Z][a-z]{1,19})(?:\s*\([^)]*\))?\s*$")

# 단독줄 패턴 전용 제외 목록 — 소제목·지명 등 인명이 아닌 단어가 false positive를
# 일으키는 것을 막는다. STRUCTURAL_MARKERS를 포함하고 추가 확장.
_HEADING_EXCLUSIONS: frozenset[str] = frozenset(STRUCTURAL_MARKERS | {
    # 지명
    "Korea", "Japan", "China", "America", "Europe", "Africa", "Asia",
    "Canada", "India", "Russia", "France", "Germany", "Britain", "England",
    "Australia", "Brazil", "Mexico", "Spain", "Italy", "Israel",
    "Iran", "Iraq", "Turkey", "Ukraine", "Singapore", "Thailand",
    "Seoul", "Tokyo", "Beijing", "London", "Paris", "Berlin",
    # 기사 소제목으로 쓰이는 주제·섹션 단어
    "Background", "History", "Introduction", "Analysis", "Overview",
    "Impact", "Effect", "Cause", "Context", "Solution", "Problem",
    "Challenge", "Benefit", "Risk", "Update", "Report", "Review",
    "Science", "Technology", "Culture", "Economy", "Politics",
    "Education", "Health", "Environment", "Society", "Nature", "Future",
    "Today", "Recently", "Meanwhile",
})


def _is_speaker_line(line: str) -> tuple[bool, str]:
    """패턴 (a) 콜론 포맷 — (화자줄 여부, 감지된 줄 원문) 반환."""
    m = _DIALOGUE_PREFIX.match(line)
    if not m:
        return False, ""
    name_part   = m.group(1).strip()
    content     = m.group(2)
    first_word  = name_part.split()[0]

    if first_word in STRUCTURAL_MARKERS:
        return False, ""
    if len(re.findall(r"\w+", content)) < _SPEAKER_CONTENT_MIN:
        return False, ""

    return True, line.strip()


def _count_heading_speakers(lines: list[str]) -> tuple[int, list[str]]:
    """패턴 (b) 단독줄 포맷 — (감지 횟수, 예시 문자열 리스트) 반환.

    이름만 있는 줄 바로 다음 비공백 줄에 _SPEAKER_CONTENT_MIN 단어 이상이면 감지.
    소제목 반복 체크: 이름(또는 접두 5자)이 다음 줄 본문에 재등장하면 소제목으로 판정해
    화자로 카운트하지 않는다.  (예: "Honesty\\nA good leader is honest." → honest ⊇ hones)
    """
    count = 0
    examples: list[str] = []
    for idx, line in enumerate(lines):
        m = _HEADING_SPEAKER.match(line)
        if not m:
            continue
        name = m.group(1)
        if name in _HEADING_EXCLUSIONS:
            continue
        # 다음 비공백 줄 찾기 (최대 2줄 안)
        next_content = ""
        for j in range(idx + 1, min(idx + 3, len(lines))):
            stripped = lines[j].strip()
            if stripped:
                next_content = stripped
                break
        if len(re.findall(r"\w+", next_content)) < _SPEAKER_CONTENT_MIN:
            continue
        # 소제목 반복 체크 — 이름이 본문에 재등장하면 소제목(topic heading)으로 판정
        name_l    = name.lower()
        content_l = next_content.lower()
        if name_l in content_l:
            continue
        if len(name_l) >= 5 and re.search(r"\b" + re.escape(name_l[:5]), content_l):
            continue
        count += 1
        if len(examples) < 2:
            examples.append(f"{name}: {next_content[:60]}")
    return count, examples


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

    # (a) 콜론 포맷
    speaker_lines: list[str] = []
    for line in lines:
        ok, matched = _is_speaker_line(line)
        if ok:
            speaker_lines.append(matched)

    # (b) 단독줄 포맷
    heading_count, heading_examples = _count_heading_speakers(lines)

    total_speakers = len(speaker_lines) + heading_count
    ratio = total_speakers / non_empty if non_empty > 0 else 0.0

    if total_speakers >= DIALOGUE_THRESHOLD:
        examples = (speaker_lines[:2] + heading_examples)[:2]
        return ClassificationResult(
            article_type=ArticleType.DIALOGUE,
            word_count=wc,
            dialogue_line_count=total_speakers,
            dialogue_line_ratio=ratio,
            dialogue_examples=examples,
            skip_cefr=True,
        )

    # ── 3. 일반 기사 ───────────────────────────────────────────────────────
    return ClassificationResult(
        article_type=ArticleType.ARTICLE,
        word_count=wc,
        dialogue_line_count=total_speakers,
        dialogue_line_ratio=ratio,
        skip_cefr=False,
    )
