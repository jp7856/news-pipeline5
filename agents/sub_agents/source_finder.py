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
KID_DOMAINS = [
    # 어린이/학생 전용 교육 뉴스
    "timeforkids.com", "dogonews.com", "kidsnews.com.au",
    "newsforkids.net", "teachingkidsnews.com", "youngzine.org",
    "snexplores.org",
    # 교육 신뢰도 최상위 (과학·문화·역사)
    "nasa.gov", "nationalgeographic.com", "smithsonianmag.com",
]

# JUNIOR 이상 시사 토픽용 확장 (2026-07-08 — 후보 도메인별 크롤 개별 검증 완료).
# 선정 기준: ①사실 보도 신뢰성(공영방송·정부·교육기관) ②학생 노출 안전성
# ③교육용 적합도 — 평이한 설명체 우선 ④Anthropic 크롤러 허용 여부 실측
# 검증 탈락: dw.com, abc.net.au — 크롤러 차단(400). 목록에 다시 넣지 말 것.
LEARNER_DOMAINS = [
    # JUNIOR+ — 학습자용·설명형 (일반 독자 대상으로 쉽게 쓰인 텍스트)
    "learningenglish.voanews.com",  # VOA 학습자용 — 낮은 난도 설명체
    "britannica.com",               # 백과 — 중립·설명체·검증된 사실
    "consumer.ftc.gov",             # 미 정부 소비자 안내 — 환불·소비자권리 등 생활 시사
    "usa.gov",                      # 미 정부 시민 안내 — 평이한 공공 설명문
]
NEWS_DOMAINS = [
    # JUNIOR_M/TIMES — 일반 보도문 허용 (공영·비영리 위주)
    "voanews.com",         # 미 공영 국제방송 — 사실 보도
    "npr.org",             # 미 공영 라디오 — 설명형 보도 강함
    "pbs.org",             # 미 공영 TV (NewsHour) — 차분한 보도체
    "cbc.ca",              # 캐나다 공영방송
    "theconversation.com", # 학자 기고 설명 저널리즘 — CC 라이선스로 인용 친화
]

# 하위 호환 별칭 (KINDER/KIDS 기본값) — 레벨별 선택은 domains_for_level()을 쓸 것
ALLOWED_DOMAINS = KID_DOMAINS


def domains_for_level(level: str) -> list[str]:
    """레벨별 출처 화이트리스트 — KINDER/KIDS는 현행 아동용 유지."""
    lv = (level or "").lower()
    if lv == "junior":
        return KID_DOMAINS + LEARNER_DOMAINS
    if lv in ("junior_m", "times"):
        return KID_DOMAINS + LEARNER_DOMAINS + NEWS_DOMAINS
    return KID_DOMAINS


def _expand_queries(
    client, topic: str, section: str, level: str,
    hint_keywords: list[str] | None, log: Callable[[str], None],
) -> list[str]:
    """토픽(한국어 가능)+섹션+레벨 → 영어 검색 질의 2~3개 (Haiku 1콜).

    핵심 규칙: 섹션은 맥락일 뿐 토픽의 의미를 덮어쓰면 안 된다 —
    진단 실측에서 "환불"(정치)이 "political refund/campaign donation refund"로
    오변환돼 출처 0건이 났던 문제의 직접 수정.
    실패 시 빈 리스트 (검색 호출이 기존처럼 자체 번역으로 폴백).
    """
    kw = f' Editor-selected keywords: {", ".join(hint_keywords[:6])}.' if hint_keywords else ""
    try:
        message = client.messages.create(
            model=CLAUDE_MODEL_FAST,
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": (
                    f"Generate 2-3 English web-search queries to find source articles for an "
                    f"educational news article.\n"
                    f"Topic (may be Korean): {topic}\n"
                    f"Category: {section or 'none'} / Student level: {level or 'unspecified'}\n"
                    f"{kw}\n"
                    f"Rules:\n"
                    f"- Translate the topic by ITS OWN everyday meaning. The category is weak "
                    f"context only — it must NEVER override or twist the topic's meaning "
                    f"(e.g. topic '환불' with category 'politics' still means CONSUMER REFUNDS, "
                    f"not political donations).\n"
                    f"- Query 1: the topic's core concept in plain English terms.\n"
                    f"- Query 2-3: alternative phrasings or a practical/explanatory angle "
                    f"(for lower student levels prefer explainer-style angles like "
                    f"'how X works' or 'X rights explained').\n"
                    f"- 2-6 words per query. No site: operators, no quotes.\n"
                    f'Output ONLY a JSON array of strings: ["...", "..."]'
                ),
            }],
        )
        text = "".join(b.text for b in message.content if b.type == "text")
        m = re.search(r"\[.*\]", text, re.DOTALL)
        queries = [q.strip() for q in json.loads(m.group(0)) if isinstance(q, str) and q.strip()]
        return queries[:3]
    except Exception as e:
        log(f"[SourceFinder] 질의 확장 실패 (검색 자체 번역으로 폴백): {e}")
        return []


def search_real_sources(
    topic: str,
    section: str = "",
    max_results: int = 3,
    hint_keywords: list[str] | None = None,
    log: Callable[[str], None] | None = None,
    level: str = "",
) -> list[dict]:
    """토픽으로 실제 기사를 웹 검색한다.

    hint_keywords: 아이디어 뱅크에서 사용자가 선택한 키워드 — 있으면 검색에 우선 활용.
    level: 레벨별 화이트리스트 선택 (KINDER/KIDS 아동용 유지, JUNIOR+ 시사 도메인 확장).
    Returns: [{"title": ..., "url": ..., "snippet": ...}, ...]
             검색 실패 시 빈 리스트 (파이프라인은 계속 진행).
    """
    _log = log or (lambda msg: logger.info(msg))
    _log("[SourceFinder] 웹 검색 시작")

    keyword_hint = ""
    if hint_keywords:
        kw_list = ", ".join(f'"{k}"' for k in hint_keywords[:6])
        keyword_hint = (
            f"\n\nIMPORTANT — The editor has pre-selected these search keywords: {kw_list}. "
            f"Use these as your primary search terms. You may refine or combine them, "
            f"but stay close to their intent."
        )

    try:
        from agents.sub_agents.usage_tracker import TrackedClient
        client = TrackedClient(api_key=ANTHROPIC_API_KEY)

        # ── 질의 확장 (Haiku 1콜) — 한국어 토픽의 의미 보존 번역 + 2~3개 변형 ──
        queries = _expand_queries(client, topic, section, level, hint_keywords, _log)
        if queries:
            _log(f"[SourceFinder] 확장 질의: {' | '.join(queries)}")
            query_block = (
                f"\n\nPrepared search queries (use #1 first; try the next one ONLY if "
                f"results are weak or empty):\n"
                + "\n".join(f"{i + 1}. {q}" for i, q in enumerate(queries))
            )
            step1 = "STEP 1 — Use the prepared queries above as your search terms."
        else:
            query_block = ""
            step1 = (
                "STEP 1 — Core keywords. If the topic is not in English, translate it "
                "first by its own everyday meaning (the category must not twist it). "
                "Extract the 2-4 ESSENTIAL keywords that define what the article must "
                "be about."
            )

        allowed = domains_for_level(level)
        message = client.messages.create(
            model=CLAUDE_MODEL_FAST,
            max_tokens=2048,
            tools=[{
                "type": "web_search_20260209",
                "name": "web_search",
                "max_uses": 2,
                "allowed_domains": allowed,
                # Haiku는 programmatic tool calling 미지원 → direct 호출로 고정해야 web_search 작동
                "allowed_callers": ["direct"],
            }],
            messages=[{
                "role": "user",
                "content": (
                    f"You are finding source references for an educational news article "
                    f"about: {topic}{f' (category: {section})' if section else ''}."
                    f"{keyword_hint}{query_block}\n\n"
                    f"{step1}\n\n"
                    f"STEP 2 — Search recent news on those terms. Prefer the last 12 "
                    f"months, newest first; avoid clearly outdated articles unless the topic "
                    f"is historical.\n\n"
                    f"STEP 3 — Read each candidate's core content and keep ONLY tight "
                    f"matches: the article's MAIN subject must clearly cover the core "
                    f"keywords, not just mention them in passing. Reject tangential or "
                    f"loosely-related articles. It is BETTER to return FEWER strongly-matched "
                    f"articles than to pad the list with weak matches. Pick from DIFFERENT "
                    f"domains — do not repeat a domain.\n\n"
                    f"Output ONLY a JSON object with up to {max_results} tightly-matched "
                    f"articles (newest first, exact URLs from your search results) and the "
                    f"candidates you rejected:\n"
                    f'{{"selected": [{{"title": "...", "url": "...", '
                    f'"snippet": "one-line summary of the article\'s core content", '
                    f'"matched_keywords": ["kw1", "kw2"], "relevance": "high|medium", '
                    f'"date": "YYYY-MM or unknown"}}], '
                    f'"rejected": [{{"title": "...", "reason": "one short line — why it is '
                    f'off-topic or weak"}}]}}\n'
                    f"Only select articles whose relevance is high or medium AND that have "
                    f"at least one matched keyword. Only use URLs that appeared in your "
                    f"search results — never invent URLs or dates (use \"unknown\" if a date "
                    f"is not shown). Output only the JSON object, no other text."
                ),
            }],
        )

        # 관측성: 실제 발행된 검색 질의 로그 (질의 품질 문제를 로그에서 보이게)
        issued = [
            getattr(b, "input", {}).get("query", "")
            for b in message.content if getattr(b, "type", "") == "server_tool_use"
        ]
        if issued:
            _log(f"[SourceFinder] 발행 질의: {' | '.join(q for q in issued if q)}")

        sources, rejected = _parse_sources(message, max_results)
        dates = ", ".join(s.get("date") or "미상" for s in sources) if sources else ""
        kws = sorted({
            k for s in sources for k in (s.get("matched_keywords") or [])
        })
        _log(
            f"[SourceFinder] 실제 출처 {len(sources)}건 검색 완료"
            + (f" (발행일: {dates})" if dates else "")
            + (f" · 매칭 키워드: {', '.join(kws)}" if kws else "")
        )
        # 관측성: 무엇이 잡혔고 왜 무관 판정됐는지 — 질의 품질 진단의 1차 신호
        if rejected:
            summary = " · ".join(
                f"{(r.get('title') or '?')[:40]}({(r.get('reason') or '?')[:60]})"
                for r in rejected[:4]
            )
            _log(f"[SourceFinder] 인용 제외 {len(rejected)}건: {summary}")
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


def _parse_sources(message, max_results: int) -> tuple[list[dict], list[dict]]:
    """응답에서 (선별 출처, 제외 후보) 목록을 추출한다.

    1차: 최종 text 블록의 JSON — {"selected": [...], "rejected": [...]} 객체
         (구형 배열-만 응답도 selected로 수용)
    2차: web_search_tool_result 블록의 원시 검색 결과 (rejected 없음)
    두 경로 모두 도메인당 1건으로 강제해 출처 편향을 방지한다.
    """
    # 1차: text 블록에서 JSON 파싱
    for block in reversed(message.content):
        if block.type != "text":
            continue
        m = re.search(r"[\[{].*[\]}]", block.text, re.DOTALL)
        if not m:
            continue
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                items = data.get("selected", [])
                rejected = [r for r in data.get("rejected", []) if isinstance(r, dict)]
            else:
                items, rejected = data, []
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
            if sources or rejected:
                return _dedup_by_domain(sources, max_results), rejected
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
    return _dedup_by_domain(candidates, max_results), []
