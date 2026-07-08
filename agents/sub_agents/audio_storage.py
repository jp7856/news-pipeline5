"""기사 오디오 저장소 추상화 — 현재 백엔드는 Railway 볼륨(로컬 디스크).

발행·서빙 코드는 이 모듈만 통해 오디오를 다룬다. 추후 R2 등 외부 스토리지로
옮길 때는 이 모듈의 함수 구현만 교체하면 된다 (호출부 변경 없음).

기사 ID = 구글 시트 행 번호(sheet_row) — 파이프라인의 기존 기사 식별자.
"""

import logging
import os

logger = logging.getLogger(__name__)

# Railway web 서비스에 볼륨이 /data로 마운트됨 (web-volume, 2026-07-08).
# 로컬 개발은 AUDIO_DIR 환경변수로 재지정.
AUDIO_DIR = os.getenv("AUDIO_DIR", "/data/audio")


def _path(article_id: int) -> str:
    return os.path.join(AUDIO_DIR, f"{int(article_id)}.mp3")


def save(article_id: int, data: bytes) -> str:
    """MP3 바이트를 저장하고 경로를 반환한다."""
    os.makedirs(AUDIO_DIR, exist_ok=True)
    path = _path(article_id)
    with open(path, "wb") as f:
        f.write(data)
    logger.info(
        f"[Audio] {article_id}.mp3 저장 ({len(data) // 1024}KB) — "
        f"볼륨 누적 {total_bytes() / 1_048_576:.1f}MB"
    )
    return path


def exists(article_id: int) -> bool:
    return os.path.isfile(_path(article_id))


def file_path(article_id: int) -> str | None:
    """서빙용 로컬 파일 경로 (없으면 None)."""
    p = _path(article_id)
    return p if os.path.isfile(p) else None


def url_path(article_id: int) -> str | None:
    """공개 URL 경로 (없으면 None). 사이트는 API_BASE + 이 값을 사용한다."""
    return f"/api/audio/{int(article_id)}.mp3" if exists(article_id) else None


def total_bytes() -> int:
    """저장된 오디오 총량 — 볼륨 사용량 페이스 확인용 (연 2.4GB 페이스 기준)."""
    if not os.path.isdir(AUDIO_DIR):
        return 0
    return sum(
        os.path.getsize(os.path.join(AUDIO_DIR, f))
        for f in os.listdir(AUDIO_DIR)
        if f.endswith(".mp3")
    )
