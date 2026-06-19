"""KeywordSuggester — 토픽/링크를 받아 연관 검색어를 카테고리별로 추천한다."""

import json
import logging
import re

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL_FAST

logger = logging.getLogger(__name__)


def suggest_keywords(topic: str, section: str = "") -> dict:
    """토픽으로 연관 검색어를 카테고리별로 생성한다.

    Returns:
        {
            "core": ["..."],        # 핵심 키워드 (3~4개)
            "angle": ["..."],       # 기사 각도/관점 (3~4개)
            "related": ["..."],     # 연관 주제 (3~4개)
            "context": ["..."],     # 배경/역사적 맥락 (2~3개)
        }
        실패 시 빈 dict.
    """
    try:
        from agents.sub_agents.usage_tracker import TrackedClient
        client = TrackedClient(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model=CLAUDE_MODEL_FAST,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": (
                    f"You are helping a children's/educational news editor brainstorm search keywords "
                    f"for an article about: {topic}"
                    + (f" (section: {section})" if section else "")
                    + "\n\n"
                    "Generate related search keywords in 4 categories. Each keyword should be a "
                    "short English search phrase (2-5 words) that could be typed into a news search engine.\n\n"
                    "Categories:\n"
                    "- core: The most essential keywords that define the main topic (3-4 items)\n"
                    "- angle: Different story angles or perspectives on this topic (3-4 items)\n"
                    "- related: Related topics, technologies, or events (3-4 items)\n"
                    "- context: Background context, history, or broader implications (2-3 items)\n\n"
                    "Output ONLY a JSON object with these exact keys. No other text.\n"
                    '{"core": [...], "angle": [...], "related": [...], "context": [...]}'
                ),
            }],
        )

        for block in reversed(message.content):
            if block.type != "text":
                continue
            m = re.search(r"\{.*\}", block.text, re.DOTALL)
            if not m:
                continue
            try:
                data = json.loads(m.group(0))
                return {
                    "core": data.get("core", []),
                    "angle": data.get("angle", []),
                    "related": data.get("related", []),
                    "context": data.get("context", []),
                }
            except json.JSONDecodeError:
                continue

        return {}
    except Exception as e:
        logger.warning(f"[KeywordSuggester] 실패: {e}")
        return {}
