"""WriterAgent — 토픽을 받아 레벨에 맞는 NE Times 기사를 작성한다."""

import logging
from typing import Callable

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, SYSTEM_PROMPT, LEVEL_CONFIG
from models import ArticleResult, Level, Section
from agents.sub_agents.utils import parse_json

logger = logging.getLogger(__name__)

# NE Times 포맷 참고 URL
NETIMES_URL = "https://www.netimes.co.kr"


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
        reference_format: str = "",
        source_content: str = "",
        real_sources: list[dict] | None = None,
    ) -> ArticleResult:
        """
        topic : 기사 주제 또는 뉴스 URL
        level : 신문 레벨 (kinder/kids/junior/times)
        section : 섹션 (과학/환경 등)
        reference_format : netimes.co.kr에서 가져온 포맷 샘플 텍스트
        real_sources : SourceFinder가 검색한 실제 기사 [{"title","url","snippet"}]
        """
        self._log(f"[Writer] 기사 작성 시작 — [{level.value}] {topic[:50]}")
        cfg = LEVEL_CONFIG[level.value]
        real_sources = real_sources or []

        format_hint = (
            f"\n\nFormat reference from NE Times:\n{reference_format[:800]}"
            if reference_format
            else ""
        )
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
CEFR level: {cfg['cefr']}
Target word count: {cfg['word_count_range']} words (Microsoft Word standard)
Paragraphs: {cfg['paragraph_count']} paragraphs of roughly equal size
{format_hint}

Instructions:
1. Search your knowledge for accurate, up-to-date information on this topic.
2. Write an article suitable for the readers' age and comprehension level.
3. Include relevant vocabulary naturally in the text.
4. Add one or two points that spark curiosity or deeper interest.
5. Include background explanations where needed for younger readers.
6. Write in a tone and style appropriate to {cfg['newspaper']}.
7. At the end, list 3–5 key vocabulary words from the article.
8. Do NOT invent or include any URLs — sources are managed separately.

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
        return result

    def _call_claude(self, prompt: str) -> dict:
        message = self._client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        return parse_json(message.content[0].text)
