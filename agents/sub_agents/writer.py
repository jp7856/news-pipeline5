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
        # 배정된 서브레벨은 작성 중 로그에 노출하지 않는다
        self._log(f"[Writer] 기사 작성 시작 — [{level.value}] {topic[:50]}")
        real_sources = real_sources or []

        source_hint = (
            f"\n\nSource article (use as factual reference — do NOT copy directly):\n{source_content[:2000]}"
            if source_content
            else ""
        )
        # 실제 검색된 기사 제목·요약을 사실 참고자료로 제공 (번호 매김 — 관련 출처 선별용)
        real_source_hint = ""
        if real_sources:
            lines = "\n".join(
                f"[{i + 1}] [{s.get('date', 'unknown')}] {s['title']}: {s['snippet']}"
                for i, s in enumerate(real_sources)
            )
            real_source_hint = (
                f"\n\nRecent real news references — for factual grounding ONLY.\n"
                f"IMPORTANT: Use these to verify facts, NOT as a writing template.\n"
                f"NEVER copy or closely paraphrase their wording — write entirely in your own original words.\n"
                f"Each reference is numbered. SOME MAY NOT actually be about this topic:\n{lines}"
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
}}

Instructions:
1. TOPIC STRICTNESS: Write ONLY about the literal subject of the topic as given.
   Never write about other events or issues where the topic word may appear as a
   metaphor or allegory (e.g. topic "mirror" → write about mirrors, NOT about
   political events described as "a mirror of society"). If the topic is in Korean,
   interpret it literally and write about that exact subject in English.
   Draw freely from your broad knowledge to write informatively — do not rely
   solely on the provided source references.
2. ORIGINAL WRITING: Write entirely in your own original words. Never copy or
   closely paraphrase any source text — this will fail the plagiarism check.
   Sources are fact-checkers only; your sentences and phrasing must be your own.
3. FACTS ONLY: every statement must be factually accurate. Never invent or
   exaggerate facts, numbers, dates, names, quotes, or events. If a detail is
   uncertain, leave it out — an article based on false information is forbidden.
4. EDUCATIONAL NEUTRALITY: this is an educational newspaper for students.
   Stay politically neutral and balanced — never take sides on partisan issues.
   No sensational, violent, sexual, or fear-mongering content or framing.
5. Write an article suitable for the readers' age and comprehension level.
6. Include relevant vocabulary naturally in the text.
7. Add one or two points that spark curiosity or deeper interest.
8. Include background explanations where needed for younger readers.
9. Write in a tone and style appropriate to {cfg['newspaper']}.
10. At the end, list 5–8 key vocabulary words from the article. For each word, include
    its CEFR level and Korean meaning in this exact format: "word CEFR · Korean_meaning"
    (e.g., "swimming A2 · 수영하다", "enormous B1 · 거대한, 어마어마한").
    Use only standard CEFR levels: A1, A2, B1, B2, C1, C2.
11. Do NOT invent or include any URLs — sources are managed separately.
12. SOURCE RELEVANCE: From the numbered references above, put in "relevant_sources"
    ONLY the numbers of references that are genuinely about THIS article's exact
    topic and could actually support its facts. If a reference is about a different
    subject (e.g. a festival when the topic is the seasons), do NOT include it.
    If none are relevant, use an empty list [] — it is perfectly fine to write the
    article from your own general knowledge with no cited sources. Never cite a
    source that does not match the article.

Respond in this exact JSON format:
{{
  "article": "<full article text with paragraphs separated by \\n\\n>",
  "vocabulary": ["swimming A2 · 수영하다", "enormous B1 · 거대한", "word3 A1 · 뜻3"],
  "relevant_sources": [1, 3]
}}

CRITICAL JSON RULES:
- Do NOT use double quotation marks (") inside any text field values.
- Replace any in-text double quotes with single quotes (') for dialogue or emphasis.
- Use only \\n\\n to separate paragraphs inside the "article" field."""

        data = self._call_claude(prompt, guidelines)

        article_text = data.get("article", "")
        vocabulary = data.get("vocabulary", [])

        # 출처는 AI 생성이 아닌 실제 검색 결과만 사용 (404 환각 방지).
        # 토픽과 맞는 출처만 인용 — Writer가 고른 relevant_sources(1-based)만 채택.
        # → 출처가 기사와 안 맞으면 인용 안 함(표절 7번 source_transparency 실패 방지).
        sources = self._select_relevant_sources(real_sources, data.get("relevant_sources"))
        available = sum(1 for s in real_sources if s.get("url"))
        if available and len(sources) < available:
            self._log(
                f"[Writer] 토픽과 무관한 출처 {available - len(sources)}건 인용 제외 "
                f"(인용 {len(sources)}/{available}건)"
            )

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
        # 사양 로그 — 서브레벨은 노출하지 않음 (CEFR·워드카운트만)
        self._log(
            f"[Writer] 사양 — {cfg['newspaper']} / CEFR {cfg['cefr']} / "
            f"워드카운트 {result.word_count} (목표 {cfg['word_count_range']}"
            f"{', 범위 내' if in_range else ' ⚠️ 범위 벗어남'})"
        )
        return result

    @staticmethod
    def _select_relevant_sources(real_sources: list[dict], relevant) -> list[str]:
        """Writer가 고른 relevant_sources(1-based 번호)에 해당하는 URL만 인용한다.

        - relevant가 리스트면 그 번호의 출처만 (토픽과 안 맞는 출처 제외).
        - relevant가 None/누락이면(구버전·파싱 실패) 전부 인용으로 안전 폴백.
        - 빈 리스트면 인용 없음(기사가 일반 지식 기반).
        """
        if relevant is None:
            return [s["url"] for s in real_sources if s.get("url")]
        chosen: list[str] = []
        for n in relevant if isinstance(relevant, list) else []:
            try:
                idx = int(n) - 1
            except (ValueError, TypeError):
                continue
            if 0 <= idx < len(real_sources):
                url = real_sources[idx].get("url")
                if url and url not in chosen:
                    chosen.append(url)
        return chosen

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

    def _call_claude(self, prompt: str, guidelines: str = "") -> dict:
    system_blocks = [
        {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
    ]
    if guidelines:
        system_blocks.append(
            {"type": "text", "text": guidelines, "cache_control": {"type": "ephemeral"}}
        )
    message = self._client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        system=system_blocks,
        messages=[{"role": "user", "content": prompt}],
    )
    return parse_json(message.content[0].text)
