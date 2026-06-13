"""Agent 3: 이미지 탐색 — Unsplash API로 기사 관련 이미지를 자동 선택한다.

변별력 원칙 (ORCHESTRATION.md 3절):
1. 관련성 우선 — AI가 기사 본문에서 시각적 핵심을 읽어 검색어를 생성한다
   (어휘 단어 나열이 아니라, 사진 에디터가 찾을 법한 구체적 장면).
2. 같은 주제로 여러 매체의 기사를 만들어도 이미지가 겹치지 않도록,
   이미 사용된 이미지를 제외하고 상위 후보 중에서 고른다.
"""

import json
import logging
import random
import re
from typing import Callable

import requests

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, SYSTEM_PROMPT, UNSPLASH_ACCESS_KEY
from models import ContentPackage

logger = logging.getLogger(__name__)

UNSPLASH_URL = "https://api.unsplash.com/search/photos"

# 검색당 받아올 후보 수 / 무작위 선택 풀 크기 (관련성 우선 — 풀을 좁게 유지)
CANDIDATES_PER_QUERY = 10
PICK_POOL_SIZE = 3


class ImageFinderAgent:
    def __init__(self, log_callback: Callable[[str], None] | None = None):
        self._log = log_callback or (lambda msg: logger.info(msg))
        from agents.sub_agents.usage_tracker import TrackedClient
        self._client = TrackedClient(api_key=ANTHROPIC_API_KEY)

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
        """관련성 우선 검색어 체인: AI 생성 검색어 → 어휘 → 토픽 → 섹션 폴백."""
        queries: list[str] = self._generate_queries(package)

        # 폴백: 어휘 2개 → 1개 → 토픽(영어일 때) → 섹션 영문명
        vocab = package.article.vocabulary
        if vocab:
            queries.append(" ".join(vocab[:2]))
            queries.append(vocab[0])
        if package.topic.isascii():
            queries.append(package.topic)
        queries.append(package.section.name.lower())
        # 중복 제거 (순서 유지)
        return list(dict.fromkeys(q for q in queries if q.strip()))

    def _generate_queries(self, package: ContentPackage) -> list[str]:
        """기사 본문을 읽고 핵심 내용과 부합하는 이미지 검색어를 생성한다."""
        try:
            prompt = f"""Read this news article and create photo search queries for Unsplash.

Topic: {package.topic}
Article:
{package.article.text[:1500]}

Rules:
- Output exactly 3 queries in English, 2-4 words each, most relevant first.
- Each query must describe the CONCRETE visual subject at the core of this
  article — what a photo editor would search for to illustrate it.
- Prefer photographable scenes/objects over abstract concepts
  (e.g. "students taking exam" not "education policy").
- Avoid proper nouns unlikely to appear in stock photos — use the general
  subject instead (e.g. "badminton player smash" not a player's name).

Output ONLY a JSON array: ["query one", "query two", "query three"]"""

            message = self._client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=200,
                system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text
            m = re.search(r"\[.*\]", raw, re.DOTALL)
            queries = [str(q).strip() for q in json.loads(m.group(0)) if str(q).strip()]
            if queries:
                self._log(f"[Agent3] AI 검색어 생성: {' | '.join(queries[:3])}")
            return queries[:3]
        except Exception as e:
            self._log(f"[Agent3] AI 검색어 생성 실패 (어휘 폴백 사용): {e}")
            return []

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
