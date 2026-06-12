"""Agent 5: 최종 검수 — ContentPackage 품질을 검토하고 승인/거부를 결정한다."""

import json
import logging
from typing import Callable

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from models import ArticleStatus, ContentPackage, ReviewResult

logger = logging.getLogger(__name__)


class ReviewerAgent:
    def __init__(self, log_callback: Callable[[str], None] | None = None):
        self._log = log_callback or (lambda msg: logger.info(msg))
        from agents.sub_agents.usage_tracker import TrackedClient
        self._client = TrackedClient(api_key=ANTHROPIC_API_KEY)

    def run(self, package: ContentPackage) -> ContentPackage:
        """ContentPackage를 검수하고 review_result를 채워 반환한다."""
        self._log("[Agent5] 최종 검수 시작")
        try:
            passed, notes = self._review(package)
            status = ArticleStatus.APPROVED if passed else ArticleStatus.REJECTED
            package.review_result = ReviewResult(passed=passed, status=status, notes=notes)
            label = "승인" if passed else f"거부 ({notes[:60]})"
            self._log(f"[Agent5] {label}")
        except Exception as e:
            self._log(f"[Agent5] 검수 오류: {e}")
            package.review_result = ReviewResult(
                passed=False,
                status=ArticleStatus.ERROR,
                notes=str(e),
            )
        self._log("[Agent5] 검수 완료")
        return package

    # ------------------------------------------------------------------

    def _review(self, pkg: ContentPackage) -> tuple[bool, str]:
        article = pkg.article
        prompt = f"""아래 NE Times 교육용 기사 패키지를 검수해주세요.

레벨: {pkg.level.value}
섹션: {pkg.section.value}
토픽: {pkg.topic}
단어수: {article.word_count}
어휘 수: {len(article.vocabulary)}
한국어 번역 여부: {"있음" if article.text_ko else "없음"}
한국어 요약 여부: {"있음" if article.summary_ko else "없음"}
이미지 URL: {pkg.image_url or "없음"}
표절 검사: {"통과" if pkg.plagiarism_report.passed else "경고"}
크로스워드 문항: {len(pkg.crossword_sentences)}개
워크북 세트: {len(pkg.workbook_sets)}개

기사 본문 (전체):
{article.text}

한국어 요약 (전체):
{article.summary_ko if article.summary_ko else "(없음)"}

다음 기준으로 평가하세요:
1. 기사 본문이 교육 목적에 적합하고 레벨에 맞는 수준인가?
2. 한국어 번역과 요약이 존재하고 자연스러운가?
3. 표절 검사를 통과했는가?
4. 크로스워드와 워크북이 생성되었는가?
5. 스팸/광고/부적절한 내용이 없는가?
6. 토픽과 섹션이 잘 어울리는가? (다소 어색해도 교육적 가치가 있으면 통과)

아래 JSON 형식으로만 응답하세요:
{{"approved": true, "reason": "판단 이유를 한 줄로"}}"""

        message = self._client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()

        data = json.loads(raw)
        return data.get("approved", False), data.get("reason", "")
