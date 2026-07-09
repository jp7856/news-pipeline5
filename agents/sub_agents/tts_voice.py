"""On Air 캐릭터 TTS — 발행 시점에 기사 영어 본문을 Google Cloud TTS로 합성한다.

캐스팅은 2026-07-08 청취 샘플(19파일)로 확정 — 조정값은 샘플 파라미터 그대로.
과금: Neural2 $16/100만 자, 무료 100만 자/월 (월 30만 자 운영 기준 ₩0).
자격증명은 시트와 같은 서비스 계정(GOOGLE_SHEETS_CREDENTIALS_JSON)을 재사용한다.
"""

import base64
import json
import logging
import re

import requests

from config import GOOGLE_SHEETS_CREDENTIALS_JSON

logger = logging.getLogger(__name__)

# 캐릭터(필자) → 확정 보이스. 키는 worksheet.BYLINE_AUTHORS의 필자명.
# 캐스팅 기록의 단일 소스는 docs/on_air_bible.md 4.4 — 변경 시 그쪽도 갱신.
# sent_break_ms: SSML 문장 사이 쉼 — 저학년(KINDER/KIDS) 500ms, JUNIOR 이상 400ms.
# 2026-07-09 실기사·샘플 청취 판정으로 rate+쉼 확정 (파일 선택 방식)
VOICE_CASTING: dict[str, dict] = {
    "Leo":    {"voice": "en-US-Wavenet-F", "pitch": 4.0,  "rate": 0.85, "sent_break_ms": 700},
    "Ruby":   {"voice": "en-US-Neural2-F", "pitch": 3.0,  "rate": 0.85, "sent_break_ms": 800},
    "Sunny":  {"voice": "en-US-Neural2-C", "pitch": 2.0,  "rate": 0.90, "sent_break_ms": 700},
    "Erin":   {"voice": "en-US-Neural2-E", "pitch": 0.0,  "rate": 0.95, "sent_break_ms": 600},
    "Daniel": {"voice": "en-US-Neural2-D", "pitch": -2.0, "rate": 1.0,  "sent_break_ms": 500},
}
DEFAULT_CASTING = {"voice": "en-US-Neural2-E", "pitch": 0.0, "rate": 1.0, "sent_break_ms": 400}

PARA_BREAK_EXTRA_MS = 300  # 문단 쉼 = 문장 쉼 + 300ms (연동 규칙)

# text:synthesize 요청당 입력 한도는 5,000바이트(SSML 태그 포함) — 여유를 두고 쪼갠다.
_CHUNK_BYTES = 4500


def _access_token() -> str:
    from google.oauth2 import service_account
    import google.auth.transport.requests

    creds_val = GOOGLE_SHEETS_CREDENTIALS_JSON
    try:
        info = json.loads(creds_val)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    except (json.JSONDecodeError, TypeError):
        creds = service_account.Credentials.from_service_account_file(
            creds_val, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&apos;"))


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _para_ssml(para: str, sent_break_ms: int) -> str:
    """한 문단을 SSML 조각으로 — 문장 사이에 <break> 삽입 (텍스트는 XML 이스케이프)."""
    sents = [s.strip() for s in _SENT_SPLIT.split(para.strip()) if s.strip()]
    brk = f'<break time="{sent_break_ms}ms"/>'
    return brk.join(_xml_escape(s) for s in sents)


def _ssml_chunks(text: str, sent_break_ms: int, para_break_ms: int | None = None) -> list[str]:
    """본문 → <speak> 청크 목록. 청크 경계는 문단 단위 — 태그를 자르지 않는다."""
    if para_break_ms is None:
        para_break_ms = sent_break_ms + PARA_BREAK_EXTRA_MS
    para_brk = f'<break time="{para_break_ms}ms"/>'
    units = [_para_ssml(p, sent_break_ms) for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    cur = ""
    for u in units:
        joined = f"{cur}{para_brk}{u}" if cur else u
        if len(f"<speak>{joined}</speak>".encode("utf-8")) <= _CHUNK_BYTES:
            cur = joined
        else:
            if cur:
                chunks.append(f"<speak>{cur}</speak>")
            cur = u
    if cur:
        chunks.append(f"<speak>{cur}</speak>")
    return chunks or [f"<speak>{_xml_escape(text)}</speak>"]


def synth_custom(text: str, voice: str, pitch: float, rate: float,
                 sent_break_ms: int, label: str = "",
                 para_break_ms: int | None = None) -> bytes:
    """SSML(문장/문단 쉼) 합성 — 캐스팅 실험용 저수준 진입점.

    para_break_ms 생략 시 문장 쉼 + 300ms 연동 규칙.
    """
    token = _access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    audio = b""
    for chunk in _ssml_chunks(text, sent_break_ms, para_break_ms):
        cfg = {"audioEncoding": "MP3", "speakingRate": rate}
        if pitch:
            cfg["pitch"] = pitch
        r = requests.post(
            "https://texttospeech.googleapis.com/v1/text:synthesize",
            headers=headers,
            json={
                "input": {"ssml": chunk},
                "voice": {"languageCode": "en-US", "name": voice},
                "audioConfig": cfg,
            },
            timeout=60,
        )
        if r.status_code != 200:
            detail = ""
            try:
                detail = r.json().get("error", {}).get("message", "")[:200]
            except Exception:
                detail = r.text[:200]
            raise RuntimeError(f"TTS {r.status_code}: {detail}")
        # 같은 인코딩 설정의 MP3 조각은 이어붙여도 재생 호환된다
        audio += base64.b64decode(r.json()["audioContent"])

    logger.info(f"[TTS] {label}({voice}) {len(text)}자 → {len(audio) // 1024}KB (SSML)")
    return audio


def synthesize(text: str, byline: str) -> bytes:
    """기사 본문(제목 포함 영어 텍스트)을 캐릭터 보이스 MP3로 합성한다.

    SSML로 문장 사이(저학년 500ms/그 외 400ms)·문단 사이(700ms) 쉼을 넣는다.
    실패 시 예외를 던진다 — 호출부(발행)는 이를 삼켜서 발행을 계속해야 한다.
    """
    cast = VOICE_CASTING.get(byline, DEFAULT_CASTING)
    return synth_custom(
        text, cast["voice"], cast["pitch"], cast["rate"],
        cast.get("sent_break_ms", 400), label=byline,
    )
