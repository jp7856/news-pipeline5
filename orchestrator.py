"""오케스트레이터 — 토픽을 받아 Agent 1(콘텐츠 제작)부터 순차적으로 파이프라인을 실행한다.

사용법:
    orchestrator = Orchestrator()
    result = orchestrator.run(
        topic="Climate change and young activists",
        level=Level.JUNIOR,
        section=Section.ENVIRONMENT,
    )
"""

import logging
import uuid
from datetime import datetime
from typing import Callable

from agents import ContentProducerAgent
from agents.translator import TranslatorAgent
from agents.image_finder import ImageFinderAgent
from agents.worksheet import WorksheetAgent
from agents.reviewer import ReviewerAgent
from models import ContentPackage, Level, Section

logger = logging.getLogger(__name__)


class PipelineCancelled(Exception):
    """사용자가 파이프라인을 중단했을 때 발생."""


class Orchestrator:
    def __init__(
        self,
        log_callback: Callable[[str], None] | None = None,
        cancel_event=None,  # threading.Event — set되면 단계 사이에서 중단
    ):
        self._log = log_callback or (lambda msg: logger.info(msg))
        self._sheet_url = ""
        self._cancel_event = cancel_event
        self._start = None

    def _check_cancel(self):
        if self._cancel_event is not None and self._cancel_event.is_set():
            raise PipelineCancelled()

    # ------------------------------------------------------------------
    # Phase 1: 기사 작성 + 표절 검사 (미리보기용)
    # ------------------------------------------------------------------
    def run_phase1(
        self,
        topic: str,
        level: Level,
        section: Section,
        source_url: str = "",
    ) -> dict:
        """기사 초안까지만 생성하고 상태를 반환한다. (이후 run_phase2로 완성)"""
        from agents.sub_agents.usage_tracker import reset_usage
        reset_usage()

        run_id = str(uuid.uuid4())[:8]
        self._start = datetime.now()
        self._log(f"=== Pipeline Start (run_id: {run_id}) ===")
        self._log(f"    Topic   : {topic}")
        self._log(f"    Level   : {level.value}")
        self._log(f"    Section : {section.value}")
        self._log("")

        producer = ContentProducerAgent(
            log_callback=self._log, cancel_check=self._check_cancel
        )
        article, plagiarism_report = producer.produce_article(
            topic, level, section, source_url=source_url
        )
        self._log("[Phase1] 기사 초안 완료 — 검토 후 '이후 작업 진행'을 눌러주세요")

        return {
            "topic": topic,
            "level": level,
            "section": section,
            "article": article,
            "plagiarism_report": plagiarism_report,
            "producer": producer,
        }

    # ------------------------------------------------------------------
    # Phase 2: 나머지 전체 (교정~검수)
    # ------------------------------------------------------------------
    def run_phase2(self, state: dict) -> tuple[ContentPackage, str]:
        """Phase 1 상태를 받아 나머지 파이프라인을 완료한다."""
        from agents.sub_agents.usage_tracker import usage_summary

        topic, level, section = state["topic"], state["level"], state["section"]
        producer: ContentProducerAgent = state["producer"]

        self._check_cancel()
        package = producer.produce_extras(
            topic, level, section, state["article"], state["plagiarism_report"]
        )

        # ── Agent 2: 한국어 번역 ──────────────────────────────────
        self._check_cancel()
        translator = TranslatorAgent(log_callback=self._log)
        package = translator.run(package)

        # ── Agent 3: 이미지 탐색 ──────────────────────────────────
        self._check_cancel()
        image_finder = ImageFinderAgent(log_callback=self._log)
        package = image_finder.run(package)

        # ── Agent 4: Google Sheets 저장 ───────────────────────────
        self._check_cancel()
        worksheet = WorksheetAgent(log_callback=self._log)
        package, sheet_url = worksheet.run(package)
        self._sheet_url = sheet_url
        self.sheet_row = worksheet.last_row  # 발행 시 상태 갱신용

        # ── Agent 5: 최종 검수 ────────────────────────────────────
        self._check_cancel()
        reviewer = ReviewerAgent(log_callback=self._log)
        package = reviewer.run(package)

        # ── 결과 요약 ─────────────────────────────────────────────
        duration = (datetime.now() - (self._start or datetime.now())).seconds
        self._log("")
        self._log(f"=== Pipeline Complete ({duration}s) ===")
        self._log(f"    Article    : {package.article.word_count} words")
        self._log(f"    Vocabulary : {len(package.article.vocabulary)} words")
        self._log(f"    Sources    : {len(package.article.sources)}")
        self._log(f"    Plagiarism : {'PASS' if package.plagiarism_report.passed else 'WARNING'}")
        self._log(f"    Edits      : {len(package.editing_suggestions)} suggestions")
        self._log(f"    Crossword  : {len(package.crossword_sentences)} pairs")
        self._log(f"    Workbook   : {len(package.workbook_sets)} sets")
        self._log(f"    Korean     : {'완료' if package.article.text_ko else '없음'}")
        self._log(f"    Image      : {'발견' if package.image_url else '없음'}")
        self._log(f"    Sheets     : {'저장완료' if self._sheet_url else '저장안됨'}")
        review = package.review_result
        self._log(f"    Review     : {'승인' if review and review.passed else '거부'} — {review.notes if review else ''}")
        self._log(f"    Cost       : {usage_summary()}")

        return package, self._sheet_url

    # ------------------------------------------------------------------
    # 전체 한 번에 실행 (CLI 호환)
    # ------------------------------------------------------------------
    def run(
        self,
        topic: str,
        level: Level,
        section: Section,
        source_url: str = "",
    ) -> tuple[ContentPackage, str]:
        state = self.run_phase1(topic, level, section, source_url=source_url)
        return self.run_phase2(state)


def print_result(pkg: ContentPackage) -> None:
    """ContentPackage 결과물을 읽기 좋게 출력한다."""
    import sys, io
    # Windows cp949 인코딩 문제 방지
    if sys.stdout.encoding and sys.stdout.encoding.lower().startswith("cp"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    sep = "-" * 60

    print(f"\n{'=' * 60}")
    print(f"  NE Times Content Package")
    print(f"  Topic   : {pkg.topic}")
    print(f"  Level   : {pkg.level.value}")
    print(f"  Section : {pkg.section.value}")
    print(f"{'=' * 60}")

    # 기사
    print(f"\n[ARTICLE] ({pkg.article.word_count} words)")
    print(sep)
    print(pkg.article.text)
    print(sep)

    # 어휘
    print(f"\n[VOCABULARY] {len(pkg.article.vocabulary)} words")
    for w in pkg.article.vocabulary:
        print(f"  - {w}")

    # 출처
    print(f"\n[SOURCES] {len(pkg.article.sources)} links")
    for s in pkg.article.sources:
        print(f"  - {s}")

    # 표절 검사
    print(f"\n[PLAGIARISM CHECK] {'PASS' if pkg.plagiarism_report.passed else 'WARNING'}")
    for key, val in pkg.plagiarism_report.checklist.items():
        status = "PASS" if val.get("pass") else "FAIL"
        print(f"  [{status}] {key}: {val.get('note', '')[:80]}")

    # 수정 제안
    print(f"\n[EDITING SUGGESTIONS] {len(pkg.editing_suggestions)} items")
    for i, s in enumerate(pkg.editing_suggestions, 1):
        print(f"  {i}. \"{s.original[:60]}...\"")
        print(f"     -> {s.suggestion[:60]}...")
        print(f"     Reason: {s.reason}")

    # 크로스워드
    print(f"\n[CROSSWORD SENTENCES] {len(pkg.crossword_sentences)} pairs")
    for c in pkg.crossword_sentences:
        print(f"  {c.word} ({c.korean_definition})")
        print(f"    B1   : {c.sentence_b1}")
        print(f"    B1-B2: {c.sentence_b1_b2}")

    # 워크북
    for ws in pkg.workbook_sets:
        print(f"\n[WORKBOOK SET {ws.set_number}]")
        print(f"  Vocab Activity: {ws.vocabulary_activity[:100]}...")
        print(f"  T/F: {len(ws.true_false)} items")
        print(f"  Comprehension: {len(ws.comprehension_questions)} questions")
        print(f"  Discussion: {len(ws.discussion_questions)} questions")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = Orchestrator().run(
        topic="Climate change and young activists",
        level=Level.JUNIOR,
        section=Section.ENVIRONMENT,
    )
    print_result(result)
