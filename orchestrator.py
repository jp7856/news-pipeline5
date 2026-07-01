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
from agents.level_agents import create_agent1, pick_sublevel
from agents.translator import TranslatorAgent
from agents.image_finder import ImageFinderAgent
from agents.worksheet import WorksheetAgent
from agents.reviewer import ReviewerAgent
from models import ArticleStatus, ContentPackage, Level, Section

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
        # 기존 기사들이 사용한 이미지 URL (대시보드가 히스토리에서 주입 — 이미지 중복 방지)
        self.used_image_urls: list[str] = []

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
        sub_level: str = "",
        hint_keywords: list[str] | None = None,
    ) -> dict:
        """기사 초안까지만 생성하고 상태를 반환한다. (이후 run_phase2로 완성)

        sub_level 미지정 시 매체 기준 레벨 범위 안에서 랜덤 배정한다.
        (작성 중 로그에는 배정된 레벨을 노출하지 않음 — 시트·결과 화면에만 기록)
        """
        from agents.sub_agents.usage_tracker import reset_usage
        reset_usage()

        randomly_assigned = not sub_level
        if randomly_assigned:
            sub_level = pick_sublevel(level)

        run_id = str(uuid.uuid4())[:8]
        self._start = datetime.now()
        self._log(f"=== Pipeline Start (run_id: {run_id}) ===")
        self._log(f"    Topic   : {topic}")
        self._log(f"    Level   : {level.value}")
        self._log(f"    Section : {section.value}")
        if randomly_assigned:
            self._log(f"[Phase1] 레벨을 선택하지 않아 랜덤으로 {sub_level} 레벨의 기사로 작성합니다.")
        self._log("")

        # 레벨에 따라 에이전트 1-1 ~ 1-5로 라우팅 (ORCHESTRATION.md 2절)
        producer = create_agent1(
            level, log_callback=self._log, cancel_check=self._check_cancel
        )
        article, plagiarism_report = producer.produce_article(
            topic, level, section, source_url=source_url, sub_level=sub_level,
            hint_keywords=hint_keywords,
        )
        self._log("[Phase1] 기사 초안 완료 — 검토 후 '이후 작업 진행'을 눌러주세요")

        return {
            "topic": topic,
            "level": level,
            "section": section,
            "sub_level": sub_level,
            "article": article,
            "plagiarism_report": plagiarism_report,
            "producer": producer,
        }

    # ------------------------------------------------------------------
    # Phase 2: 나머지 전체 (교정~검수)
    # ------------------------------------------------------------------
    def run_phase2(self, state: dict) -> tuple[ContentPackage, str]:
        """Phase 1 상태를 받아 나머지 파이프라인을 완료한다."""
        from agents.sub_agents.usage_tracker import usage_summary, usage_cost

        topic, level, section = state["topic"], state["level"], state["section"]
        producer: ContentProducerAgent = state["producer"]

        self._check_cancel()
        package = producer.produce_extras(
            topic, level, section, state["article"], state["plagiarism_report"],
            sub_level=state.get("sub_level", "L2"),
        )
        package.sub_level = state.get("sub_level", "L2")

        # ── Agent 2: 한국어 번역 ──────────────────────────────────
        self._check_cancel()
        translator = TranslatorAgent(log_callback=self._log)
        package = translator.run(package)

        # ── Agent 3: 이미지 탐색 (기존 기사 이미지 제외 — 매체별 변별력) ──
        self._check_cancel()
        image_finder = ImageFinderAgent(log_callback=self._log)
        package = image_finder.run(package, exclude_urls=self.used_image_urls)

        # ── Agent 5: 최종 검수 (거부 시 자동 재작성, 최대 2회) ────
        self._check_cancel()
        reviewer = ReviewerAgent(log_callback=self._log)
        package = reviewer.run(package)

        max_retries = 2
        attempt = 0
        while (
            package.review_result is not None
            and not package.review_result.passed
            and package.review_result.status == ArticleStatus.REJECTED  # 검수 오류는 재작성 대상 아님
            and attempt < max_retries
        ):
            attempt += 1
            self._check_cancel()
            package = self._fix_rejected(package, producer, translator, attempt, max_retries)
            self._check_cancel()
            package = reviewer.run(package)

        review = package.review_result
        if review is not None and not review.passed and attempt >= max_retries:
            self._log(f"[Phase2] 재작성 {max_retries}회 후에도 검수 거부 — '검수거부' 상태로 저장합니다")

        # ── Agent 4: Google Sheets 저장 (검수 결과 반영) ──────────
        self._check_cancel()
        self.cost_krw = usage_cost()["krw"]
        worksheet = WorksheetAgent(log_callback=self._log)
        package, sheet_url = worksheet.run(package, cost_krw=self.cost_krw)
        self._sheet_url = sheet_url
        self.sheet_row = worksheet.last_row  # 발행 시 상태 갱신용

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
    # 검수 거부 시 재작성 — fix_targets에 해당하는 부분만 재생성
    # ------------------------------------------------------------------
    def _fix_rejected(
        self, package: ContentPackage, producer, translator, attempt: int, max_retries: int
    ) -> ContentPackage:
        review = package.review_result
        targets = list(review.fix_targets) if review.fix_targets else ["article"]
        self._log(
            f"[Phase2] 검수 거부 — 재작성 {attempt}/{max_retries}회 "
            f"(대상: {', '.join(targets)} / 사유: {review.notes[:80]})"
        )

        if "article" in targets:
            from agents.sub_agents.reviser import ReviserAgent
            from agents.sub_agents.utils import sl_aim_hint
            from config import SUBLEVEL_CONFIG
            reviser = ReviserAgent(log_callback=self._log)
            instruction = (
                f"REVISION REQUEST: The article was rejected by the final reviewer "
                f"for the following reason(s):\n{review.notes}\n\n"
                f"You MUST rewrite the article to fix every issue listed above — "
                f"this is the top priority and is non-negotiable. "
                f"While fixing the listed issues, also maintain: "
                f"factual accuracy, source alignment, and appropriate reading level."
            )
            # sl(평균 문장 길이) 위반이 거부 사유에 있을 때만 조준점 추가 —
            # wc/인용/표절 등 다른 사유에는 불필요. 조준점 없이 "줄여라"만 받으면
            # Reviser가 과도하게 잘라 반대쪽 하한을 뚫는 현상(21.0→11.4)을 방지.
            if "문장 길이" in (review.notes or ""):
                sl_range = SUBLEVEL_CONFIG.get(package.level.value, {}).get(
                    package.sub_level, {}
                ).get("sentence_length", "")
                if sl_range:
                    aim = sl_aim_hint(sl_range, package.level.value)
                    instruction += (
                        f"\n\nFor the sentence-length issue specifically: aim for "
                        f"{aim} — do not overcorrect past the opposite end of the range."
                    )
                    self._log(f"[Phase2] Reviser sl 재작성 조준점: {aim}")
            article, _reply, changed = reviser.run(
                package.article, instruction, package.level,
                plagiarism_report=package.plagiarism_report,
                sub_level=package.sub_level,
            )
            if _reply:
                self._log(f"[Reviser] 설명: {_reply[:120]}")
            if changed:
                package.article = article
                package.plagiarism_report = producer._plagcheck.run(article)
                if "translation" not in targets:
                    targets.append("translation")  # 본문이 바뀌면 번역도 갱신

        if "translation" in targets:
            package = translator.run(package)

        if "crossword" in targets:
            package.crossword_sentences = producer._crossword.run(package.article)

        if "workbook" in targets:
            package.workbook_sets = producer._workbook.run(package.article, package.level)

        return package

    # ------------------------------------------------------------------
    # 전체 한 번에 실행 (CLI 호환)
    # ------------------------------------------------------------------
    def run(
        self,
        topic: str,
        level: Level,
        section: Section,
        source_url: str = "",
        sub_level: str = "",
    ) -> tuple[ContentPackage, str]:
        state = self.run_phase1(topic, level, section, source_url=source_url, sub_level=sub_level)
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
