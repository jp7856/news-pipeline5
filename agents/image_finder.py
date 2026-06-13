"""Agent 3: 이미지 탐색 — Unsplash API로 기사 관련 이미지를 자동 선택한다.

변별력 원칙 (ORCHESTRATION.md 3절): 같은 주제로 여러 매체의 기사를 만들어도
이미지가 겹치지 않도록, 이미 사용된 이미지를 제외하고 상위 후보 중에서 고른다.
"""

import logging
import random
from typing import Callable

import requests

from config import UNSPLASH_ACCESS_KEY
from models import ContentPackage

logger = logging.getLogger(__name__)

UNSPLASH_URL = "https://api.unsplash.com/search/photos"

# 검색당 받아올 후보 수 / 무작위 선택 풀 크기
CANDIDATES_PER_QUERY = 10
PICK_POOL_SIZE = 5


class ImageFinderAgent:
    def __init__(self, log_callback: Callable[[str], None] | None = None):
        self._log = log_callback or (lambda msg: logger.info(msg))

    def run(self, package: ContentPackage, exclude_urls: list[str] | None = None) -> ContentPackage:
        """기사 이미지를 찾는다. exclude_urls(기존 기사들이 쓴 이미지)는 제외한다."""
        self._log("[Agent3] 이미지 탐색 시작")
        exclude = {self._normalize(u) for u in (exclude_urls or []) if u}
        if exclude:
            self._log(f"[Agent3] 기존 기사 이미지 {len(exclude)}건 제외 목록 적용")

        for query in self._build_queries(package):
            self._log(f"[Agent3] 검색어: {query}")
            try:
                candidates = self._search_images(query)
            except Exception as e:
                self._log(f"[Agent3] 이미지 탐색 오류: {e}")
                break

            fresh = [u for u in candidates if self._normalize(u) not in exclude]
            if fresh:
                # 첫 결과 고정 대신 상위 후보 중 무작위 — 매체별 변별력 확보
                package.image_url = random.choice(fresh[:PICK_POOL_SIZE])
                self._log(
                    f"[Agent3] 이미지 발견 (후보 {len(candidates)}건, 중복 제외 {len(fresh)}건 중 선택): "
                    f"{package.image_url[:80]}..."
                )
                break
            if candidates:
                self._log(f"[Agent3] 후보 {len(candidates)}건 모두 기존 기사와 중복 — 다음 검색어로")
        else:
            self._log("[Agent3] 이미지를 찾지 못했습니다.")
        self._log("[Agent3] 이미지 탐색 완료")
        return package

    @staticmethod
    def _normalize(url: str) -> str:
        """Unsplash URL의 쿼리스트링(크기 파라미터 등)을 제거해 같은 사진을 식별한다."""
        return url.split("?")[0]

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

    def _search_images(self, query: str) -> list[str]:
        """검색 결과 이미지 URL 후보 목록을 반환한다."""
        if not UNSPLASH_ACCESS_KEY:
            return []
        resp = requests.get(
            UNSPLASH_URL,
            params={"query": query, "per_page": CANDIDATES_PER_QUERY, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return [r["urls"]["regular"] for r in results if r.get("urls", {}).get("regular")]
