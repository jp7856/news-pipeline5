"""Agent 1: ContentProducerAgent — NE Times 콘텐츠 제작 파이프라인 코디네이터.

흐름:
  WriterAgent → PlagiarismCheckerAgent → EditorAgent
                                              ↓
                          [병렬] CrosswordAgent + WorkbookAgent
                                              ↓
                                      ContentPackage 반환
"""

import logging
from typing import Callable

import anthropic
import requests
from bs4 import BeautifulSoup

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from models import ContentPackage, Level, Section
from agents.sub_agents import (
    WriterAgent,
    PlagiarismCheckerAgent,
    EditorAgent,
    CrosswordAgent,
    WorkbookAgent,
)

logger = logging.getLogger(__name__)

NETIMES_SAMPLE_URL = "https://www.netimes.co.kr"


class ContentProducerAgent:
    def __init__(
        self,
        log_callback: Callable[[str], None] | None = None,
        cancel_check: Callable[[], None] | None = None,
    ):
        self._log = log_callback or (lambda msg: logger.info(msg))
        self._cancel_check = cancel_check or (lambda: None)
        from agents.sub_agents.usage_tracker import TrackedClient
        self._client = TrackedClient(api_key=ANTHROPIC_API_KEY)
        self._reference_format_cache: str = ""

        # 서브에이전트 초기화 (클라이언트 공유)
        self._writer    = WriterAgent(self._client, log_callback=self._log)
        self._plagcheck = PlagiarismCheckerAgent(self._client, log_callback=self._log)
        self._editor    = EditorAgent(self._client, log_callback=self._log)
        self._crossword = CrosswordAgent(self._client, log_callback=self._log)
        self._workbook  = WorkbookAgent(self._client, log_callback=self._log)

    def produce_article(
        self, topic: str, level: Level, section: Section, source_url: str = ""
    ):
        """Phase 1 — 기사 작성 + 표절 검사까지만 수행한다.

        Returns: (article, plagiarism_report)
        """
        self._log(f"[Agent1] 콘텐츠 제작 시작 — [{level.value}/{section.value}] {topic[:60]}")

        # NE Times 포맷 참고 (캐시 활용)
        reference = self._get_reference_format()

        # 링크가 있으면 원문 스크래핑
        source_content = ""
        if source_url:
            source_content = self._scrape_article(source_url)

        self._cancel_check()

        # 실제 기사 출처 검색 (AI가 URL을 지어내는 환각 방지)
        from agents.sub_agents.source_finder import search_real_sources
        real_sources = search_real_sources(topic, section.value, log=self._log)

        self._cancel_check()

        # ── Step 1: 기사 작성 ─────────────────────────────────────
        article = self._writer.run(
            topic, level, section,
            reference_format=reference,
            source_content=source_content,
            real_sources=real_sources,
        )

        # 사용자가 직접 넣은 링크도 출처에 포함
        if source_url and source_url not in article.sources:
            article.sources.insert(0, source_url)

        self._cancel_check()

        # ── Step 2: 표절 검사 ─────────────────────────────────────
        plagiarism_report = self._plagcheck.run(article)

        if not plagiarism_report.passed:
            self._cancel_check()
            self._log("[Agent1] 표절 위험 감지 — 기사 재작성 시도")
            revised_topic = (
                f"{topic}\n\n"
                f"[REVISION NOTE] The previous version had plagiarism issues: "
                f"{plagiarism_report.notes}. "
                f"Please rewrite with stronger paraphrasing and structural originality."
            )
            article = self._writer.run(
                revised_topic, level, section,
                reference_format=reference,
                source_content=source_content,
                real_sources=real_sources,
            )
            plagiarism_report = self._plagcheck.run(article)

        return article, plagiarism_report

    def produce_extras(
        self, topic: str, level: Level, section: Section, article, plagiarism_report
    ) -> ContentPackage:
        """Phase 2 — 교정 + 크로스워드 + 워크북을 수행하고 패키지를 완성한다."""
        # ── Step 3: 교정 ──────────────────────────────────────────
        editing_suggestions = self._editor.run(article, level)

        # 교정 제안을 본문에 자동 반영 (원문 구절이 그대로 존재할 때만)
        applied = 0
        for s in editing_suggestions:
            if s.original and s.original in article.text:
                article.text = article.text.replace(s.original, s.suggestion, 1)
                applied += 1
        if applied:
            article.word_count = len(article.text.split())
            self._log(f"[Agent1] 교정 {applied}건 본문 반영 완료")

        # ── Step 4 & 5: 크로스워드 + 워크북 (독립 실행) ──────────
        self._cancel_check()
        crossword_sentences = self._crossword.run(article)
        self._cancel_check()
        workbook_sets       = self._workbook.run(article, level)

        self._log(
            f"[Agent1] 완료 — "
            f"기사 {article.word_count}단어 / "
            f"표절 {'통과' if plagiarism_report.passed else '경고'} / "
            f"수정제안 {len(editing_suggestions)}건 / "
            f"크로스워드 {len(crossword_sentences)}개 / "
            f"워크북 {len(workbook_sets)}세트"
        )

        return ContentPackage(
            topic=topic,
            level=level,
            section=section,
            article=article,
            plagiarism_report=plagiarism_report,
            editing_suggestions=editing_suggestions,
            crossword_sentences=crossword_sentences,
            workbook_sets=workbook_sets,
        )

    def run(self, topic: str, level: Level, section: Section, source_url: str = "") -> ContentPackage:
        """전체 한 번에 실행 (하위 호환용)."""
        article, plagiarism_report = self.produce_article(
            topic, level, section, source_url=source_url
        )
        return self.produce_extras(topic, level, section, article, plagiarism_report)

    # ------------------------------------------------------------------

    def _scrape_article(self, url: str) -> str:
        """URL에서 기사 본문을 추출한다."""
        self._log(f"[Agent1] 링크 스크래핑 시작: {url[:80]}")
        try:
            resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            soup = BeautifulSoup(resp.text, "lxml")

            # 스크립트·스타일 제거
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            # 본문 단락 추출
            paragraphs = [
                p.get_text(strip=True)
                for p in soup.find_all("p")
                if len(p.get_text(strip=True)) > 40
            ]
            content = "\n\n".join(paragraphs[:30])
            self._log(f"[Agent1] 스크래핑 완료 — {len(content)}자")
            return content[:3000]  # 토큰 절약을 위해 최대 3000자
        except Exception as e:
            self._log(f"[Agent1] 스크래핑 실패 (무시하고 계속): {e}")
            return ""

    def _get_reference_format(self) -> str:
        """netimes.co.kr에서 샘플 기사 텍스트를 가져온다 (세션 중 1회 캐시)."""
        if self._reference_format_cache:
            return self._reference_format_cache
        try:
            resp = requests.get(
                NETIMES_SAMPLE_URL,
                timeout=8,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            soup = BeautifulSoup(resp.text, "lxml")
            # 기사 본문처럼 보이는 텍스트 추출 (p 태그)
            texts = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 40]
            self._reference_format_cache = "\n".join(texts[:15])
            self._log(f"[Agent1] NE Times 포맷 참고 로드 완료 ({len(texts)}개 단락)")
        except Exception as e:
            self._log(f"[Agent1] NE Times 포맷 로드 실패 (무시하고 계속): {e}")
            self._reference_format_cache = ""
        return self._reference_format_cache
