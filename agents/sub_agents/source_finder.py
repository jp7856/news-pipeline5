"""SourceFinder — Claude 웹 검색 도구로 토픽 관련 실제 기사 URL을 검색한다.

AI가 출처 URL을 지어내는 환각 문제를 방지하기 위해,
기사 작성 전에 실제 존재하는 뉴스 기사를 웹 검색으로 찾아 출처로 사용한다.

참고: Google Custom Search API는 신규 고객에게 폐쇄되어 사용 불가.
Claude의 서버사이드 web_search 도구를 사용한다 (검색 1,000회당 $10).
"""

import json
import logging
import re
from typing import Callable

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

logger = logging.getLogger(__name__)

# 출처로 허용할 교육용 뉴스 + 접근 가능한 신뢰 사이트
# (BBC/Reuters/Guardian/NYT/AP는 Anthropic 크롤러를 차단해 사용 불가)
ALLOWED_DOMAINS = [
    # 어린이/학생 교육용 뉴스
    "timeforkids.com", "dogonews.com", "kidsnews.com.au",
    "newsforkids.net", "teachingkidsnews.com", "youngzine.org",
    "snexplores.org", "kids.nationalgeographic.com",
    # 신뢰 가능한 일반 사이트
    "time.com", "npr.org", "smithsonianmag.com",
    "nasa.gov", "nationalgeographic.com", "sciencedaily.com",
]


def search_real_sources(
    topic: str,
    section: str = "",
    max_results: int = 3,
    log: Callable[[str], None] | None = None,
) -> list[dict]:
    """토픽으로 실제 기사를 웹 검색한다.

    Returns: [{"title": ..., "url": ..., "snippet": ...}, ...]
             검색 실패 시 빈 리스트 (파이프라인은 계속 진행).
    """
    _log = log or (lambda msg: logger.info(msg))
    _log("[SourceFinder] 웹 검색 시작")

    try:
        from agents.sub_agents.usage_tracker import TrackedClient
        client = TrackedClient(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            tools=[{
                "type": "web_search_20260209",
                "name": "web_search",
                "max_uses": 2,
                "allowed_domains": ALLOWED_DOMAINS,
            }],
            messages=[{
                "role": "user",
                "content": (
                    f"Search the web for recent news articles about: {topic}"
                    f"{f' (category: {section})' if section else ''}. "
                    f"If the topic is not in English, translate it to English first "
                    f"and search with the English query.\n\n"
                    f"After searching, output ONLY a JSON array of the {max_results} best "
                    f"articles you found, using the exact URLs from your search results:\n"
                    f'[{{"title": "...", "url": "...", "snippet": "one-line summary"}}]\n'
                    f"Output only the JSON array, no other text. "
                    f"Only include URLs that appeared in your search results — never invent URLs."
                ),
            }],
        )

        sources = _parse_sources(message, max_results)
        _log(f"[SourceFinder] 실제 출처 {len(sources)}건 검색 완료")
        return sources
    except Exception as e:
        _log(f"[SourceFinder] 검색 실패 (무시하고 계속): {e}")
        return []


def _parse_sources(message, max_results: int) -> list[dict]:
    """응답에서 출처 목록을 추출한다.

    1차: 최종 text 블록의 JSON 배열 (모델이 검색 결과에서 선별한 것)
    2차: web_search_tool_result 블록의 원시 검색 결과
    """
    # 1차: text 블록에서 JSON 배열 파싱
    for block in reversed(message.content):
        if block.type != "text":
            continue
        m = re.search(r"\[.*\]", block.text, re.DOTALL)
        if not m:
            continue
        try:
            items = json.loads(m.group(0))
            sources = [
                {
                    "title": it.get("title", ""),
                    "url": it.get("url", ""),
                    "snippet": it.get("snippet", ""),
                }
                for it in items
                if isinstance(it, dict) and it.get("url", "").startswith("http")
            ]
            if sources:
                return sources[:max_results]
        except (json.JSONDecodeError, AttributeError):
            continue

    # 2차: 원시 검색 결과 블록
    sources: list[dict] = []
    seen: set[str] = set()
    for block in message.content:
        if block.type != "web_search_tool_result":
            continue
        results = block.content
        if not isinstance(results, list):
            continue
        for r in results:
            url = getattr(r, "url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            sources.append({
                "title": getattr(r, "title", ""),
                "url": url,
                "snippet": "",
            })
            if len(sources) >= max_results:
                return sources
    return sources
