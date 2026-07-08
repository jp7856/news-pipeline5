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

# 모델별 단가 (USD / 1M tokens)
PRICING = {
    "claude-sonnet-4-6": {
        "input": 3.00, "output": 15.00,
        "cache_write": 3.75, "cache_read": 0.30,
    },
    "claude-haiku-4-5-20251001": {
        "input": 0.25, "output": 1.25,
        "cache_write": 0.30, "cache_read": 0.03,
    },
}
# 알 수 없는 모델은 Sonnet 단가로 fallback
DEFAULT_PRICING = PRICING["claude-sonnet-4-6"]

PRICE_WEB_SEARCH = 10.00 / 1000  # 검색 1회당 USD
USD_TO_KRW = 1400

_lock = threading.Lock()
_totals = {
    "calls": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_write_tokens": 0,
    "cache_read_tokens": 0,
    "web_searches": 0,
    "cost_usd": 0.0,  # 모델별 단가 적용 누적 비용
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

    model = getattr(message, "model", "") or ""
    # 모델명 부분 매칭 (응답에 전체 모델명이 오는 경우 대비)
    price = DEFAULT_PRICING
    for key, p in PRICING.items():
        if key in model:
            price = p
            break

    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    cw  = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cr  = getattr(usage, "cache_read_input_tokens", 0) or 0
    server = getattr(usage, "server_tool_use", None)
    ws = getattr(server, "web_search_requests", 0) or 0 if server else 0

    cost = (
        inp / 1_000_000 * price["input"]
        + out / 1_000_000 * price["output"]
        + cw  / 1_000_000 * price["cache_write"]
        + cr  / 1_000_000 * price["cache_read"]
        + ws * PRICE_WEB_SEARCH
    )

    with _lock:
        _totals["calls"] += 1
        _totals["input_tokens"] += inp
        _totals["output_tokens"] += out
        _totals["cache_write_tokens"] += cw
        _totals["cache_read_tokens"] += cr
        _totals["web_searches"] += ws
        _totals["cost_usd"] += cost


def usage_cost() -> dict:
    """현재까지 누적 추정 비용을 숫자로 반환한다 (시트 기록·대시보드 표시용)."""
    with _lock:
        usd = _totals["cost_usd"]
    return {"usd": round(usd, 4), "krw": round(usd * USD_TO_KRW)}


def usage_summary() -> str:
    """누적 사용량과 추정 비용 문자열을 반환한다."""
    with _lock:
        t = dict(_totals)

    cost_usd = t["cost_usd"]
    cost_krw = cost_usd * USD_TO_KRW

    return (
        f"API {t['calls']}회 / "
        f"입력 {t['input_tokens']:,} / 출력 {t['output_tokens']:,} / "
        f"캐시쓰기 {t['cache_write_tokens']:,} / 캐시읽기 {t['cache_read_tokens']:,} / "
        f"웹검색 {t['web_searches']}회 → "
        f"${cost_usd:.4f} (약 {cost_krw:,.0f}원)"
    )


# ------------------------------------------------------------------
# TTS 사용량 — 월 누계를 볼륨에 영속화 (Claude 사용량과 달리 실행 단위 리셋 없음)
# ------------------------------------------------------------------

import json as _json
import os as _os
from datetime import datetime as _dt

TTS_FREE_CHARS_MONTH = 1_000_000          # Neural2 무료 할당량 (자/월)
TTS_PRICE_USD_PER_CHAR = 16.0 / 1_000_000  # 무료 한도 초과분 단가

def _tts_usage_path() -> str:
    from agents.sub_agents.audio_storage import AUDIO_DIR
    return _os.path.join(AUDIO_DIR, "_tts_usage.json")


def _tts_load() -> dict:
    try:
        with open(_tts_usage_path(), encoding="utf-8") as f:
            return _json.load(f)
    except (OSError, _json.JSONDecodeError):
        return {}


def record_tts_chars(n: int) -> None:
    """이번 달 TTS 합성 문자 수를 누적 기록한다 (볼륨의 JSON 파일)."""
    month = _dt.now().strftime("%Y-%m")
    with _lock:
        data = _tts_load()
        data[month] = int(data.get(month, 0)) + int(n)
        try:
            _os.makedirs(_os.path.dirname(_tts_usage_path()), exist_ok=True)
            with open(_tts_usage_path(), "w", encoding="utf-8") as f:
                _json.dump(data, f)
        except OSError as e:
            # 기록 실패가 발행/TTS를 막으면 안 된다
            import logging
            logging.getLogger(__name__).warning(f"TTS 사용량 기록 실패: {e}")


def tts_usage() -> dict:
    """이번 달 TTS 사용량 — 무료 한도 대비 %와 초과분 예상 비용 포함."""
    month = _dt.now().strftime("%Y-%m")
    chars = int(_tts_load().get(month, 0))
    over = max(0, chars - TTS_FREE_CHARS_MONTH)
    return {
        "month": month,
        "chars": chars,
        "free_limit_pct": round(chars / TTS_FREE_CHARS_MONTH * 100, 1),
        "est_usd": round(over * TTS_PRICE_USD_PER_CHAR, 4),
        "est_krw": round(over * TTS_PRICE_USD_PER_CHAR * USD_TO_KRW),
    }


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