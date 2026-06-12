"""사용량 추적 — 파이프라인 실행당 Claude API 토큰 사용량과 비용을 집계한다.

사용법:
    from agents.sub_agents.usage_tracker import TrackedClient, reset_usage, usage_summary

    client = TrackedClient(anthropic.Anthropic(api_key=...))  # 기존 client 대신
    reset_usage()        # 파이프라인 시작 시
    ... 파이프라인 실행 ...
    print(usage_summary())  # 종료 시
"""

import threading

import anthropic

# Claude Sonnet 4.6 단가 (USD / 1M tokens)
PRICE_INPUT = 3.00
PRICE_OUTPUT = 15.00
PRICE_CACHE_WRITE = 3.75   # 입력의 1.25배
PRICE_CACHE_READ = 0.30    # 입력의 0.1배
PRICE_WEB_SEARCH = 10.00 / 1000  # 검색 1회당 USD

USD_TO_KRW = 1400  # 대략 환율

_lock = threading.Lock()
_totals = {
    "calls": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_write_tokens": 0,
    "cache_read_tokens": 0,
    "web_searches": 0,
}


def reset_usage() -> None:
    with _lock:
        for k in _totals:
            _totals[k] = 0


def record_usage(message) -> None:
    """API 응답의 usage를 누적한다."""
    usage = getattr(message, "usage", None)
    if usage is None:
        return
    with _lock:
        _totals["calls"] += 1
        _totals["input_tokens"] += getattr(usage, "input_tokens", 0) or 0
        _totals["output_tokens"] += getattr(usage, "output_tokens", 0) or 0
        _totals["cache_write_tokens"] += getattr(usage, "cache_creation_input_tokens", 0) or 0
        _totals["cache_read_tokens"] += getattr(usage, "cache_read_input_tokens", 0) or 0
        # 서버사이드 웹 검색 횟수
        server = getattr(usage, "server_tool_use", None)
        if server is not None:
            _totals["web_searches"] += getattr(server, "web_search_requests", 0) or 0


def usage_summary() -> str:
    """누적 사용량과 추정 비용 문자열을 반환한다."""
    with _lock:
        t = dict(_totals)

    cost_usd = (
        t["input_tokens"] / 1_000_000 * PRICE_INPUT
        + t["output_tokens"] / 1_000_000 * PRICE_OUTPUT
        + t["cache_write_tokens"] / 1_000_000 * PRICE_CACHE_WRITE
        + t["cache_read_tokens"] / 1_000_000 * PRICE_CACHE_READ
        + t["web_searches"] * PRICE_WEB_SEARCH
    )
    cost_krw = cost_usd * USD_TO_KRW

    return (
        f"API {t['calls']}회 / "
        f"입력 {t['input_tokens']:,} / 출력 {t['output_tokens']:,} / "
        f"캐시쓰기 {t['cache_write_tokens']:,} / 캐시읽기 {t['cache_read_tokens']:,} / "
        f"웹검색 {t['web_searches']}회 → "
        f"${cost_usd:.4f} (약 {cost_krw:,.0f}원)"
    )


# ------------------------------------------------------------------
# Anthropic 클라이언트 래퍼 — messages.create 호출을 가로채 사용량 기록
# ------------------------------------------------------------------

class _TrackedMessages:
    def __init__(self, inner):
        self._inner = inner

    def create(self, **kwargs):
        message = self._inner.create(**kwargs)
        record_usage(message)
        return message

    def __getattr__(self, name):
        return getattr(self._inner, name)


class TrackedClient:
    """anthropic.Anthropic을 감싸 messages.create 사용량을 자동 기록한다."""

    def __init__(self, client: anthropic.Anthropic | None = None, api_key: str | None = None):
        self._client = client or anthropic.Anthropic(api_key=api_key)
        self.messages = _TrackedMessages(self._client.messages)

    def __getattr__(self, name):
        return getattr(self._client, name)
