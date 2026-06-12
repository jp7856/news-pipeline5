"""WriterAgent — 토픽을 받아 레벨에 맞는 NE Times 기사를 작성한다."""

import logging
import re
from typing import Callable

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    SYSTEM_PROMPT,
    LEVEL_CONFIG,
    SUBLEVEL_CONFIG,
    DEFAULT_SUBLEVEL,
)
from models import ArticleResult, Level, Section
from agents.sub_agents.utils import parse_json

logger = logging.getLogger(__name__)

class WriterAgent:
    def __init__(
        self,
        client: anthropic.Anthropic,
        log_callback: Callable[[str], None] | None = None,
    ):
        self._client = client
        self._log = log_callback or (lambda msg: logger.info(msg))

    def run(
        self,
        topic: str,
        level: Level,
        section: Section,
        source_content: str = "",
        real_sources: list[dict] | None = None,
        guidelines: str = "",
        sub_level: str = DEFAULT_SUBLEVEL,
    ) -> ArticleResult:
        """
        topic : 기사 주제 또는 뉴스 URL
        level : 신문 레벨 (kinder/kids/junior/times/junior_m)
        section : 섹션 (과학/환경 등)
        real_sources : SourceFinder가 검색한 실제 기사 [{"title","url","snippet"}]
        guidelines : 신문별 작성 지침 (agents/guidelines/*.md 본문 — 에이전트 1-X가 주입)
        sub_level : 매체 내부 서브레벨 (L1/L2/L3 — SUBLEVEL_CONFIG가 사양을 덮어씀)
        """
        cfg, sub_level = self._merge_config(level, sub_level)
        self._log(f"[Writer] 기사 작성 시작 — [{level.value} {sub_level}] {topic[:50]}")
        real_sources = real_sources or []

        source_hint = (
            f"\n\nSource article (use as factual reference — do NOT copy directly):\n{source_content[:2000]}"
            if source_content
            else ""
        )
        # 실제 검색된 기사 제목·요약을 사실 참고자료로 제공
        real_source_hint = ""
        if real_sources:
            lines = "\n".join(
                f"- {s['title']}: {s['snippet']}" for s in real_sources
            )
            real_source_hint = (
                f"\n\nRecent real news references on this topic (for factual grounding):\n{lines}"
            )

        prompt = f"""You are writing an article for {cfg['newspaper']}.
{source_hint}{real_source_hint}

Topic: {topic}
Section: {section.value}
Target readers: {cfg['target']}
Sub-level within this newspaper: {sub_level}
CEFR level: {cfg['cefr']}
Word count: {cfg['word_count_range']} words — the total MUST fall within this range (Microsoft Word standard)
Average sentence length: {cfg.get('sentence_length', 'appropriate to the level')} — keep the article average within this range
Paragraphs: {cfg['paragraph_count']} short paragraphs (1–3 sentences each, like a real newspaper)
{self._guideline_hint(guidelines, cfg)}

Instructions:
1. Search your knowledge for accurate, up-to-date information on this topic.
2. FACTS ONLY: every statement must be factually accurate. Never invent or
   exaggerate facts, numbers, dates, names, quotes, or events. If a detail is
   uncertain, leave it out — an article based on false information is forbidden.
3. EDUCATIONAL NEUTRALITY: this is an educational newspaper for students.
   Stay politically neutral and balanced — never take sides on partisan issues.
   No sensational, violent, sexual, or fear-mongering content or framing.
4. Write an article suitable for the readers' age and comprehension level.
5. Include relevant vocabulary naturally in the text.
6. Add one or two points that spark curiosity or deeper interest.
7. Include background explanations where needed for younger readers.
8. Write in a tone and style appropriate to {cfg['newspaper']}.
9. At the end, list 3–5 key vocabulary words from the article.
10. Do NOT invent or include any URLs — sources are managed separately.

Respond in this exact JSON format:
{{
  "article": "<full article text with paragraphs separated by \\n\\n>",
  "vocabulary": ["word1", "word2", "word3", "word4", "word5"]
}}

CRITICAL JSON RULES:
- Do NOT use double quotation marks (") inside any text field values.
- Replace any in-text double quotes with single quotes (') for dialogue or emphasis.
- Use only \\n\\n to separate paragraphs inside the "article" field."""

        data = self._call_claude(prompt)

        article_text = data.get("article", "")
        vocabulary = data.get("vocabulary", [])

        # 출처는 AI 생성이 아닌 실제 검색 결과만 사용 (404 환각 방지)
        sources = [s["url"] for s in real_sources if s.get("url")]

        result = ArticleResult(
            text=article_text,
            vocabulary=vocabulary[:8],
            sources=sources,
        )
        self._log(
            f"[Writer] 완료 — {result.word_count}단어 / "
            f"어휘 {len(result.vocabulary)}개 / 출처 {len(result.sources)}개"
        )
        in_range = self._word_count_in_range(result.word_count, cfg["word_count_range"])
        self._log(
            f"[Writer] 사양 — {cfg['newspaper']} {sub_level} / CEFR {cfg['cefr']} / "
            f"워드카운트 {result.word_count} (목표 {cfg['word_count_range']}"
            f"{', 범위 내' if in_range else ' ⚠️ 범위 벗어남'})"
        )
        return result

    @staticmethod
    def _word_count_in_range(count: int, range_str: str) -> bool:
        """'150–190' 형식의 범위 문자열에 단어 수가 들어가는지 확인."""
        try:
            lo, hi = re.split(r"[–\-~]", range_str)
            return int(lo) <= count <= int(hi)
        except (ValueError, AttributeError):
            return True  # 범위를 못 읽으면 경고하지 않음

    @staticmethod
    def _merge_config(level: Level, sub_level: str) -> tuple[dict, str]:
        """LEVEL_CONFIG 위에 서브레벨 사양을 덮어 최종 cfg를 만든다.

        해당 매체에 없는 서브레벨(예: kinder L3)이면 DEFAULT_SUBLEVEL로 폴백.
        """
        base = LEVEL_CONFIG[level.value]
        subs = SUBLEVEL_CONFIG.get(level.value, {})
        if sub_level not in subs:
            sub_level = DEFAULT_SUBLEVEL
        return {**base, **subs.get(sub_level, {})}, sub_level

    @staticmethod
    def _guideline_hint(guidelines: str, cfg: dict) -> str:
        if not guidelines:
            return ""
        return (
            f"\n\nNewspaper-specific writing guidelines for {cfg['newspaper']} "
            f"(follow these strictly — they take priority over general instructions below):\n"
            f"{guidelines}"
        )

    def _call_claude(self, prompt: str) -> dict:
        message = self._client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        return parse_json(message.content[0].text)
