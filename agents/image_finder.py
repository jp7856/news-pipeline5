"""Agent 3: 이미지 탐색 — Unsplash API로 기사 관련 이미지를 자동 선택한다."""

import logging
from typing import Callable

import requests

from config import UNSPLASH_ACCESS_KEY
from models import ContentPackage

logger = logging.getLogger(__name__)

UNSPLASH_URL = "https://api.unsplash.com/search/photos"


class ImageFinderAgent:
    def __init__(self, log_callback: Callable[[str], None] | None = None):
        self._log = log_callback or (lambda msg: logger.info(msg))

    def run(self, package: ContentPackage) -> ContentPackage:
        self._log("[Agent3] 이미지 탐색 시작")
        for query in self._build_queries(package):
            self._log(f"[Agent3] 검색어: {query}")
            try:
                url = self._search_image(query)
                if url:
                    package.image_url = url
                    self._log(f"[Agent3] 이미지 발견: {url[:80]}...")
                    break
            except Exception as e:
                self._log(f"[Agent3] 이미지 탐색 오류: {e}")
                break
        else:
            self._log("[Agent3] 이미지를 찾지 못했습니다.")
        self._log("[Agent3] 이미지 탐색 완료")
        return package

    def _build_queries(self, package: ContentPackage) -> list[str]:
        """넓은 검색 → 좁은 검색 순서의 폴백 체인을 만든다."""
        vocab = package.article.vocabulary
        queries: list[str] = []
        # 어휘 4개 AND 검색은 결과가 없는 경우가 많아 2개 → 1개 순으로 좁힌다
        if vocab:
            queries.append(" ".join(vocab[:2]))
            queries.append(vocab[0])
        # 토픽이 영어(ASCII)면 마지막 폴백으로 사용
        if package.topic.isascii():
            queries.append(package.topic)
        # 그래도 없으면 섹션 영문명으로 폴백
        queries.append(package.section.name.lower())
        # 중복 제거 (순서 유지)
        return list(dict.fromkeys(q for q in queries if q.strip()))

    def _search_image(self, query: str) -> str | None:
        if not UNSPLASH_ACCESS_KEY:
            return None
        resp = requests.get(
            UNSPLASH_URL,
            params={"query": query, "per_page": 1, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            return results[0]["urls"]["regular"]
        return None
