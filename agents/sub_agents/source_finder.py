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
from urllib.parse import urlparse

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL_FAST

logger = logging.getLogger(__name__)

# 출처로 허용할 교육용 뉴스 + 교육 신뢰도 최상위 사이트
# (BBC/Reuters/Guardian/NYT/AP는 Anthropic 크롤러를 차단해 사용 불가 — 넣으면 400)
# wired.com / popularmechanics.com 제거 — Anthropic 크롤러 차단(400)
# sciencedaily.com 제외 — 연구 논문 보도자료만 모아두는 사이트라 교육용 기사 아님
# mentalfloss.com 제외 — 트리비아·엔터테인먼트 리스티클 중심, 교육용 부적합
# sciencenewsforstudents.org 제외 — snexplores.org로 리다이렉트되는 구 도메인(중복)
# livescience/earth/space/discovermagazine/worldwildlife 제외 — 일반 독자 대상,
#   교육 신뢰도 검증 범위를 NASA·NatGeo·Smithsonian로 좁힘
# kids.nationalgeographic.com 제거 — nationalgeographic.com이 상위 도메인 포함(중복)
ALLOWED_DOMAINS = [
    # 어린이/학생 전용 교육 뉴스
    "timeforkids.com", "dogonews.com", "kidsnews.com.au",
    "newsforkids.net", "teachingkidsnews.com", "youngzine.org",
    "snexplores.org",
    # 교육 신뢰도 최상위 (과학·문화·역사)
    "nasa.gov", "nationalgeographic.com", "smithsonianmag.com",
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
            model=CLAUDE_MODEL_FAST,
            max_tokens=2048,
            tools=[{
                "type": "web_search_20260209",
                "name": "web_search",
                "max_uses": 1,
                "allowed_domains": ALLOWED_DOMAINS,
            }],
            messages=[{
                "role": "user",
                "content": (
                    f"You are finding source references for an educational news article "
                    f"about: {topic}{f' (category: {section})' if section else ''}.\n\n"
                    f"STEP 1 — Core keywords. If the topic is not in English, translate it "
                    f"first. Extract the 2-4 ESSENTIAL keywords that define what the article "
                    f"must be about.\n\n"
                    f"STEP 2 — Search recent news on those keywords. Prefer the last 12 "
                    f"months, newest first; avoid clearly outdated articles unless the topic "
                    f"is historical.\n\n"
                    f"STEP 3 — Read each candidate's core content and keep ONLY tight "
                    f"matches: the article's MAIN subject must clearly cover the core "
                    f"keywords, not just mention them in passing. Reject tangential or "
                    f"loosely-related articles. It is BETTER to return FEWER strongly-matched "
                    f"articles than to pad the list with weak matches. Pick from DIFFERENT "
                    f"domains — do not repeat a domain.\n\n"
                    f"Output ONLY a JSON array of up to {max_results} tightly-matched "
                    f"articles, newest first, using the exact URLs from your search "
                    f"results:\n"
                    f'[{{"title": "...", "url": "...", '
                    f'"snippet": "one-line summary of the article\'s core content", '
                    f'"matched_keywords": ["kw1", "kw2"], "relevance": "high|medium", '
                    f'"date": "YYYY-MM or unknown"}}]\n'
                    f"Only include articles whose relevance is high or medium AND that have "
                    f"at least one matched keyword. Only use URLs that appeared in your "
                    f"search results — never invent URLs or dates (use \"unknown\" if a date "
                    f"is not shown). Output only the JSON array, no other text."
                ),
            }],
        )

        sources = _parse_sources(message, max_results)
        dates = ", ".join(s.get("date") or "미상" for s in sources) if sources else ""
        kws = sorted({
            k for s in sources for k in (s.get("matched_keywords") or [])
        })
        _log(
            f"[SourceFinder] 실제 출처 {len(sources)}건 검색 완료"
            + (f" (발행일: {dates})" if dates else "")
            + (f" · 매칭 키워드: {', '.join(kws)}" if kws else "")
        )
        return sources
    except Exception as e:
        _log(f"[SourceFinder] 검색 실패 (무시하고 계속): {e}")
        return []


def _domain_of(url: str) -> str:
    """URL에서 비교용 도메인을 추출한다 (www. 제거)."""
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return url
    return host[4:] if host.startswith("www.") else host


def _dedup_by_domain(sources: list[dict], max_results: int) -> list[dict]:
    """도메인당 최대 1건만 남겨 출처 편향(한 도메인 독점)을 방지한다."""
    out: list[dict] = []
    seen_domains: set[str] = set()
    for s in sources:
        d = _domain_of(s.get("url", ""))
        if not d or d in seen_domains:
            continue
        seen_domains.add(d)
        out.append(s)
        if len(out) >= max_results:
            break
    return out


def _parse_sources(message, max_results: int) -> list[dict]:
    """응답에서 출처 목록을 추출한다.

    1차: 최종 text 블록의 JSON 배열 (모델이 검색 결과에서 선별한 것)
    2차: web_search_tool_result 블록의 원시 검색 결과
    두 경로 모두 도메인당 1건으로 강제해 출처 편향을 방지한다.
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
                    "date": it.get("date", "unknown"),
                    "matched_keywords": it.get("matched_keywords", []),
                    "relevance": (it.get("relevance") or "").lower(),
                }
                for it in items
                if isinstance(it, dict) and it.get("url", "").startswith("http")
                # 토픽 핵심 키워드와 실제로 매칭된 기사만 — 느슨하게 관련된 것 제외
                and it.get("relevance", "high") != "low"
                and (it.get("matched_keywords") or it.get("relevance") is None)
            ]
            if sources:
                return _dedup_by_domain(sources, max_results)
        except (json.JSONDecodeError, AttributeError):
            continue

    # 2차: 원시 검색 결과 블록 — 후보를 모두 모은 뒤 도메인당 1건으로 추림
    candidates: list[dict] = []
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
            candidates.append({
                "title": getattr(r, "title", ""),
                "url": url,
                "snippet": "",
                "date": "unknown",
            })
    return _dedup_by_domain(candidates, max_results)
