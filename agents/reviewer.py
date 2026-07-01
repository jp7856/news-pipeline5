"""Agent 5: 최종 검수 — ContentPackage 품질을 검토하고 승인/거부를 결정한다."""

import logging
from typing import Callable

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from models import ArticleStatus, ContentPackage, ReviewResult
from agents.sub_agents.utils import call_claude_json

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
            passed, notes, fix_targets = self._review(package)
            status = ArticleStatus.APPROVED if passed else ArticleStatus.REJECTED
            package.review_result = ReviewResult(
                passed=passed, status=status, notes=notes, fix_targets=fix_targets
            )
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

    FIX_TARGETS = ("article", "translation", "crossword", "workbook")

    def _review(self, pkg: ContentPackage) -> tuple[bool, str, list]:
        article = pkg.article

        # 해당 신문(레벨)의 작성 지침 마크다운을 검수 기준으로도 강제한다.
        # → 지침에 쓴 규칙이 Writer뿐 아니라 검수에서도 지켜야 하는 규칙이 된다.
        from agents.content_producer import load_guideline_body
        from agents.level_agents import guideline_file_for_level

        guideline = load_guideline_body(guideline_file_for_level(pkg.level))
        guideline_block = guideline_criterion = ""

        # 워드카운트는 config(단일 기준)의 해당 서브레벨 목표 범위로 검사한다.
        # LLM 계수는 부정확하므로 코드로 직접 판정해 범위 밖이면 강제 거부한다.
        from agents.sub_agents.writer import WriterAgent
        cfg, _ = WriterAgent._merge_config(pkg.level, pkg.sub_level)
        wc_range = cfg.get("word_count_range", "")
        wc_in_range = WriterAgent._word_count_in_range(article.word_count, wc_range)
        sl_range = cfg.get("sentence_length", "")
        avg_sl = WriterAgent._avg_sentence_length(article.text)
        sl_in_range = WriterAgent._sentence_length_in_range(avg_sl, sl_range)
        if guideline:
            guideline_block = (
                f"\n이 신문의 작성 지침 (기사는 아래 지침을 반드시 준수해야 함):\n"
                f"-----\n{guideline}\n-----\n"
            )
            guideline_criterion = (
                '\n9. 위 "작성 지침"을 준수했는가? (문체·어휘·문단 구성·금지 사항 등 '
                '지침을 명백히 위반하면 거부하고 fix_targets에 "article"을 넣으세요. '
                '단, 지침에 인용·귀속 표현(quoted/attributed statement, "Experts say" 등) '
                '요건이 있어도 이것만으로는 거부하지 마세요 — 인용 유무 판정은 이 검수의 '
                '대상이 아닙니다. 기사에 인용이 자연스럽게 포함돼 있으면 그대로 두고, '
                '없어도 문제 삼지 마세요. 이 판정은 추후 별도 시스템이 전담합니다.)'
            )

        prompt = f"""아래 NE Times 교육용 기사 패키지를 검수해주세요.

레벨: {pkg.level.value}
섹션: {pkg.section.value}
토픽: {pkg.topic}
단어수: {article.word_count} (목표 범위: {wc_range or "지정 없음"}{"" if wc_in_range else " ⚠️ 범위 벗어남 → 거부 대상"})
평균 문장 길이: {avg_sl:.1f}단어 (목표 범위: {sl_range or "지정 없음"}{"" if sl_in_range else " ⚠️ 범위 벗어남 → 거부 대상"})
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
{guideline_block}
다음 기준으로 평가하세요:
1. 기사 본문이 교육 목적에 적합하고 레벨에 맞는 수준인가?
2. 기사 내용이 사실에 부합하는가? (명백한 허위·날조·과장된 수치나 인용의 징후가 있으면 거부)
3. 정치 편향적이거나 선정적인 내용이 없는가? (교육용 신문 — 당파적 논조, 선정·폭력·공포 조장 금지)
4. 한국어 번역과 요약이 존재하고 자연스러운가?
5. 표절 검사를 통과했는가?
6. 크로스워드와 워크북이 생성되었는가?
7. 스팸/광고/부적절한 내용이 없는가?
8. 토픽과 섹션이 잘 어울리는가? (다소 어색해도 교육적 가치가 있으면 통과){guideline_criterion}

아래 JSON 형식으로만 응답하세요. 거부(approved=false)인 경우 fix_targets에
재작성이 필요한 부분을 골라 넣으세요 (선택지: "article", "translation", "crossword", "workbook"):
{{"approved": true, "reason": "판단 이유를 한 줄로", "fix_targets": []}}"""

        data = call_claude_json(
            self._client, self._log, "Agent5",
            model=CLAUDE_MODEL, max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        approved = data.get("approved", False)
        reason = data.get("reason", "")
        fix_targets = [t for t in data.get("fix_targets", []) if t in self.FIX_TARGETS]

        # 코드 레벨 강제: 워드카운트·평균 문장 길이·CEFR이 목표 범위를 벗어나면 LLM 판정과 무관하게 거부.
        # → _fix_rejected가 이 사유로 기사를 재작성한다(최대 2회).
        from agents.level_agents import cefr_key_for
        from agents.sub_agents.cefr_checker import validate as cefr_validate
        from agents.sub_agents.article_classifier import classify as classify_article
        cefr_key = cefr_key_for(pkg.level, pkg.sub_level)
        if cefr_key is None:
            self._log(f"[Agent5] CEFR 검증 건너뜀 — {pkg.level.value} {pkg.sub_level} 임계값 미설정")
            cefr_result = None
        else:
            art_cls = classify_article(article.text, cefr_key)
            if art_cls.skip_cefr:
                self._log(art_cls.build_log("Agent5"))
                cefr_result = None
            else:
                cefr_result = cefr_validate(article.text, cefr_key)

        if not wc_in_range:
            approved = False
            wc_note = f"워드카운트 {article.word_count}단어가 목표 범위({wc_range})를 벗어남 — 범위 안으로 분량 조정 필요"
            reason = f"{wc_note}. {reason}" if reason else wc_note
            if "article" not in fix_targets:
                fix_targets.append("article")
        if not sl_in_range:
            approved = False
            sl_note = f"평균 문장 길이 {avg_sl:.1f}단어가 목표 범위({sl_range})를 벗어남 — 문장 길이 조정 필요(난이도/CEFR)"
            reason = f"{sl_note}. {reason}" if reason else sl_note
            if "article" not in fix_targets:
                fix_targets.append("article")
        if cefr_result and not cefr_result.passed:
            approved = False
            cefr_note = f"CEFR 난이도 위반({'; '.join(cefr_result.violations[:2])})"
            reason = f"{cefr_note}. {reason}" if reason else cefr_note
            if "article" not in fix_targets:
                fix_targets.append("article")

        return approved, reason, fix_targets
