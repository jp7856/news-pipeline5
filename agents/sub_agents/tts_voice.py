"""On Air 캐릭터 TTS — 발행 시점에 기사 영어 본문을 Google Cloud TTS로 합성한다.

캐스팅은 2026-07-08 청취 샘플(19파일)로 확정 — 조정값은 샘플 파라미터 그대로.
과금: Neural2 $16/100만 자, 무료 100만 자/월 (월 30만 자 운영 기준 ₩0).
자격증명은 시트와 같은 서비스 계정(GOOGLE_SHEETS_CREDENTIALS_JSON)을 재사용한다.
"""

import base64
import json
import logging

import requests

from config import GOOGLE_SHEETS_CREDENTIALS_JSON

logger = logging.getLogger(__name__)

# 캐릭터(필자) → 확정 보이스. 키는 worksheet.BYLINE_AUTHORS의 필자명.
# 캐스팅 기록의 단일 소스는 docs/on_air_bible.md 4.4 — 변경 시 그쪽도 갱신.
VOICE_CASTING: dict[str, dict] = {
    "Leo":    {"voice": "en-US-Wavenet-F", "pitch": 4.0,  "rate": 0.85},  # 2026-07-08 재캐스팅·속도 확정
    "Ruby":   {"voice": "en-US-Neural2-F", "pitch": 3.0,  "rate": 0.95},  # 2026-07-09 속도 조정
    "Sunny":  {"voice": "en-US-Neural2-C", "pitch": 2.0,  "rate": 1.0},   # 2026-07-09 속도 조정
    "Erin":   {"voice": "en-US-Neural2-E", "pitch": 0.0,  "rate": 0.97},
    "Daniel": {"voice": "en-US-Neural2-D", "pitch": -2.0, "rate": 0.95},
}
DEFAULT_CASTING = {"voice": "en-US-Neural2-E", "pitch": 0.0, "rate": 1.0}

# text:synthesize 요청당 입력 한도는 5,000바이트 — 여유를 두고 문단 단위로 쪼갠다.
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


def _chunks(text: str) -> list[str]:
    """문단 경계로 나눠 각 조각을 요청 한도 이내로 유지한다."""
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    cur = ""
    for p in paras:
        joined = f"{cur}\n\n{p}" if cur else p
        if len(joined.encode("utf-8")) <= _CHUNK_BYTES:
            cur = joined
        else:
            if cur:
                chunks.append(cur)
            cur = p
    if cur:
        chunks.append(cur)
    return chunks or [text]


def synthesize(text: str, byline: str) -> bytes:
    """기사 본문(제목 포함 영어 텍스트)을 캐릭터 보이스 MP3로 합성한다.

    실패 시 예외를 던진다 — 호출부(발행)는 이를 삼켜서 발행을 계속해야 한다.
    """
    cast = VOICE_CASTING.get(byline, DEFAULT_CASTING)
    token = _access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    audio = b""
    for chunk in _chunks(text):
        cfg = {"audioEncoding": "MP3", "speakingRate": cast["rate"]}
        if cast["pitch"]:
            cfg["pitch"] = cast["pitch"]
        r = requests.post(
            "https://texttospeech.googleapis.com/v1/text:synthesize",
            headers=headers,
            json={
                "input": {"text": chunk},
                "voice": {"languageCode": "en-US", "name": cast["voice"]},
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

    logger.info(f"[TTS] {byline}({cast['voice']}) {len(text)}자 → {len(audio) // 1024}KB")
    return audio
