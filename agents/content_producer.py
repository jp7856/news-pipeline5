"""Agent 1: ContentProducerAgent — NE Times 콘텐츠 제작 파이프라인 코디네이터.

흐름:
  WriterAgent → PlagiarismCheckerAgent → EditorAgent
                                              ↓
                          [병렬] CrosswordAgent + WorkbookAgent
                                              ↓
                                      ContentPackage 반환
"""

import logging
import re
from pathlib import Path
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

GUIDELINES_DIR = Path(__file__).parent / "guidelines"


def load_guideline_body(guideline_file: str | None) -> str:
    """지침 마크다운 본문(HTML 주석 제거)을 반환한다.

    파일명이 없거나, 파일을 못 읽거나, 주석을 뺀 본문이 비면 빈 문자열.
    Writer(작성)와 Reviewer(검수)가 같은 지침을 공유하기 위한 단일 진입점.
    """
    if not guideline_file:
        return ""
    path = GUIDELINES_DIR / guideline_file
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL).strip()


class ContentProducerAgent:
    # 레벨별 서브클래스(agents/level_agents.py)가 재정의
    AGENT_LABEL: str = "Agent1"
    GUIDELINE_FILE: str | None = None  # agents/guidelines/ 아래 지침 마크다운 파일명

    def __init__(
        self,
        log_callback: Callable[[str], None] | None = None,
        cancel_check: Callable[[], None] | None = None,
    ):
        self._log = log_callback or (lambda msg: logger.info(msg))
        self._cancel_check = cancel_check or (lambda: None)
        from agents.sub_agents.usage_tracker import TrackedClient
        self._client = TrackedClient(api_key=ANTHROPIC_API_KEY)
        self._guidelines = self._load_guidelines()

        # 서브에이전트 초기화 (클라이언트 공유)
        from agents.sub_agents.fact_checker import FactCheckerAgent
        self._writer    = WriterAgent(self._client, log_callback=self._log)
        self._plagcheck = PlagiarismCheckerAgent(self._client, log_callback=self._log)
        self._factcheck = FactCheckerAgent(self._client, log_callback=self._log)
        self._editor    = EditorAgent(self._client, log_callback=self._log)
        self._crossword = CrosswordAgent(self._client, log_callback=self._log)
        self._workbook  = WorkbookAgent(self._client, log_callback=self._log)

    def produce_article(
        self, topic: str, level: Level, section: Section, source_url: str = "",
        sub_level: str = "L2",
    ):
        """Phase 1 — 기사 작성 + 표절 검사까지만 수행한다.

        Returns: (article, plagiarism_report)
        """
        # 배정된 서브레벨은 작성 중 로그에 노출하지 않는다 (시트·결과 화면에만 기록)
        self._log(f"[{self.AGENT_LABEL}] 콘텐츠 제작 시작 — [{level.value}/{section.value}] {topic[:60]}")
        if self._guidelines:
            self._log(f"[{self.AGENT_LABEL}] 작성 지침 적용 ({self.GUIDELINE_FILE}, {len(self._guidelines)}자)")

        # 링크가 있으면 원문 스크래핑 (http(s) URL일 때만 — 토픽이 잘못 들어오는 경우 방지)
        source_content = ""
        if source_url and not source_url.lower().startswith("http"):
            self._log(f"[{self.AGENT_LABEL}] 링크 입력이 URL이 아니라 무시: {source_url[:60]}")
            source_url = ""
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
            source_content=source_content,
            real_sources=real_sources,
            guidelines=self._guidelines,
            sub_level=sub_level,
        )

        # 사용자가 직접 넣은 링크도 출처에 포함
        if source_url and source_url not in article.sources:
            article.sources.insert(0, source_url)

        self._cancel_check()

        # ── Step 2: 표절 검사 + 워드카운트 (둘 다 만족할 때까지 재작성, 최대 3회) ──
        # 초안 단계에서 분량을 맞춘다 — 범위 밖 초안을 검토에 넘기지 않기 위함.
        # 목표 범위는 config가 단일 기준 (Writer·검수와 동일 소스).
        _cfg, _ = self._writer._merge_config(level, sub_level)
        wc_range = _cfg.get("word_count_range", "")

        plagiarism_report = self._plagcheck.run(article)
        max_retries = 3
        attempt = 0
        while attempt < max_retries:
            wc_ok = self._writer._word_count_in_range(article.word_count, wc_range)
            if plagiarism_report.passed and wc_ok:
                break
            attempt += 1
            self._cancel_check()

            notes: list[str] = []
            if not plagiarism_report.passed:
                failed_items = "\n".join(
                    f"- {key}: {val.get('note', '')}"
                    for key, val in plagiarism_report.checklist.items()
                    if not val.get("pass")
                )
                self._log(f"[{self.AGENT_LABEL}] 표절 위험 감지 — 재작성 {attempt}/{max_retries}회")
                # 어느 부분이 걸렸는지 로그에 명시
                for key, val in plagiarism_report.checklist.items():
                    if not val.get("pass"):
                        self._log(f"[{self.AGENT_LABEL}]   ⤷ 걸린 항목: {key} — {val.get('note', '')[:120]}")
                if plagiarism_report.notes:
                    self._log(f"[{self.AGENT_LABEL}]   ⤷ 비고: {plagiarism_report.notes[:120]}")
                notes.append(
                    f"The previous version failed these plagiarism checks:\n{failed_items}\n"
                    f"Notes: {plagiarism_report.notes}\n"
                    f"Fix each failed item specifically. Use stronger paraphrasing, "
                    f"original sentence structure, and your own framing of the facts."
                )
            if not wc_ok:
                self._log(
                    f"[{self.AGENT_LABEL}] 워드카운트 {article.word_count} 목표({wc_range}) 벗어남 "
                    f"— 재작성 {attempt}/{max_retries}회"
                )
                notes.append(
                    f"The article has {article.word_count} words, which is OUTSIDE the required "
                    f"range of {wc_range} words. Adjust the length to fall WITHIN {wc_range} words "
                    f"— keep the reading level, the facts, and fully original wording."
                )

            revised_topic = (
                f"{topic}\n\n[REVISION NOTE — attempt {attempt}]\n" + "\n\n".join(notes)
            )
            article = self._writer.run(
                revised_topic, level, section,
                source_content=source_content,
                real_sources=real_sources,
                guidelines=self._guidelines,
                sub_level=sub_level,
            )
            plagiarism_report = self._plagcheck.run(article)

        if not plagiarism_report.passed:
            self._log(
                f"[{self.AGENT_LABEL}] 재작성 {max_retries}회 후에도 표절 경고 잔류 — "
                f"AI 수정 채팅으로 직접 수정하거나 새로 생성해주세요"
            )
        if not self._writer._word_count_in_range(article.word_count, wc_range):
            self._log(
                f"[{self.AGENT_LABEL}] 재작성 {max_retries}회 후에도 워드카운트 {article.word_count} "
                f"범위({wc_range}) 미달 — AI 수정 채팅으로 분량을 조정하거나 새로 생성해주세요"
            )

        # ── Step 3: 사실 점검 — 출처 대조 (불일치 시 1회 재작성 + 표절 재검사) ──
        self._cancel_check()
        fact_passed, issues = self._factcheck.run(article, real_sources)
        if not fact_passed:
            for issue in issues:
                self._log(f"[{self.AGENT_LABEL}]   ⤷ 사실 점검 지적: {issue[:150]}")
            self._log(f"[{self.AGENT_LABEL}] 사실 점검 불일치 — 출처에 맞게 재작성 1회")
            issues_block = "\n".join(f"- {i}" for i in issues)
            fact_topic = (
                f"{topic}\n\n"
                f"[FACT-CHECK NOTE] The previous draft failed fact verification "
                f"against the source articles:\n{issues_block}\n"
                f"Rewrite the article so every claim is consistent with the sources. "
                f"Remove or correct any numbers, dates, names, or quotes that the "
                f"sources do not support — never invent specifics. "
                f"Keep the article within {wc_range} words."
            )
            self._cancel_check()
            article = self._writer.run(
                fact_topic, level, section,
                source_content=source_content,
                real_sources=real_sources,
                guidelines=self._guidelines,
                sub_level=sub_level,
            )
            # 수정 후 표절 재검사 원칙 유지
            plagiarism_report = self._plagcheck.run(article)
            fact_passed, issues = self._factcheck.run(article, real_sources)
            if not fact_passed:
                self._log(
                    f"[{self.AGENT_LABEL}] 사실 점검 의심 항목 잔류 — "
                    f"미리보기에서 확인 후 AI 수정 채팅으로 보완해주세요"
                )

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
            self._log(f"[{self.AGENT_LABEL}] 교정 {applied}건 본문 반영 완료")

        # ── Step 4 & 5: 크로스워드 + 워크북 (병렬 실행 — 서로 독립적) ──
        self._cancel_check()
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_cw = executor.submit(self._crossword.run, article)
            future_wb = executor.submit(self._workbook.run, article, level)
            crossword_sentences = future_cw.result()
            workbook_sets       = future_wb.result()

        self._log(
            f"[{self.AGENT_LABEL}] 완료 — "
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

    def _load_guidelines(self) -> str:
        """지침 마크다운을 읽어 반환한다. HTML 주석을 제거한 본문이 비면 빈 문자열.

        규칙은 ORCHESTRATION.md 3절 참조 — 본문 전체가 Writer 프롬프트에 주입된다.
        """
        if self.GUIDELINE_FILE and not (GUIDELINES_DIR / self.GUIDELINE_FILE).exists():
            self._log(f"[{self.AGENT_LABEL}] 지침 파일 없음 (기본 프롬프트 사용): {self.GUIDELINE_FILE}")
            return ""
        return load_guideline_body(self.GUIDELINE_FILE)

    def _scrape_article(self, url: str) -> str:
        """URL에서 기사 본문을 추출한다."""
        self._log(f"[{self.AGENT_LABEL}] 링크 스크래핑 시작: {url[:80]}")
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
            self._log(f"[{self.AGENT_LABEL}] 스크래핑 완료 — {len(content)}자")
            return content[:3000]  # 토큰 절약을 위해 최대 3000자
        except Exception as e:
            self._log(f"[{self.AGENT_LABEL}] 스크래핑 실패 (무시하고 계속): {e}")
            return ""

