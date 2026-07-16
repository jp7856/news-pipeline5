"""Agent 1: ContentProducerAgent — JP Times 콘텐츠 제작 파이프라인 코디네이터.

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
from agents.sub_agents.utils import sl_aim_hint

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
        self._skip_stats: dict[str, int] = {"BRIEF": 0, "DIALOGUE": 0}
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
        sub_level: str = "L2", hint_keywords: list[str] | None = None,
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
        real_sources = search_real_sources(
            topic, section.value, hint_keywords=hint_keywords, log=self._log,
            level=level.value,  # 레벨별 화이트리스트 (JUNIOR+ 시사 도메인 확장)
        )

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

        # ── Step 2: 표절 + 워드카운트 + 평균 문장 길이 + CEFR (넷 다 만족할 때까지 재작성, 최대 3회) ──
        # 초안 단계에서 분량·난이도를 맞춘다 — 범위 밖 초안을 검토에 넘기지 않기 위함.
        # 목표 범위는 config가 단일 기준 (Writer·검수와 동일 소스).
        from agents.level_agents import cefr_key_for
        from agents.sub_agents.cefr_checker import validate as cefr_validate, build_feedback as cefr_feedback
        from agents.sub_agents.article_classifier import classify as classify_article
        _cfg, _ = self._writer._merge_config(level, sub_level)
        wc_range = _cfg.get("word_count_range", "")
        sl_range = _cfg.get("sentence_length", "")
        cefr_key = cefr_key_for(level, sub_level)
        if cefr_key is None:
            self._log(f"[{self.AGENT_LABEL}] CEFR 검증 건너뜀 — {level.value} {sub_level} 임계값 미설정")

        plagiarism_report = self._plagcheck.run(article)
        max_retries = 3
        attempt = 0
        # 승계 경고 — 한 번이라도 걸린 게이트는 이후 재작성 지시에 계속 병기한다
        # (예: 1차에서 날조를 고치고 2차에서 sl만 남았을 때, 인용을 다시 넣는 재발 차단)
        carry: dict[str, str] = {}
        prev_sl_side: str | None = None
        while attempt < max_retries:
            wc_ok = self._writer._word_count_in_range(article.word_count, wc_range)
            avg_sl = self._writer._avg_sentence_length(article.text)
            sl_ok = self._writer._sentence_length_in_range(avg_sl, sl_range)
            art_cls = classify_article(article.text, cefr_key) if cefr_key else None
            if art_cls and art_cls.skip_cefr:
                log_msg = art_cls.build_log(self.AGENT_LABEL)
                if log_msg:
                    self._log(log_msg)
                self._skip_stats[art_cls.article_type.value] = \
                    self._skip_stats.get(art_cls.article_type.value, 0) + 1
                cefr_result = None
                cefr_ok = True
            else:
                cefr_result = cefr_validate(article.text, cefr_key) if cefr_key else None
                cefr_ok = cefr_result.passed if cefr_result is not None else True
            if plagiarism_report.passed and wc_ok and sl_ok and cefr_ok:
                break
            # sl 진동 감지 — 직전 시도와 반대 방향으로 목표 구간을 건너뛰었으면
            # (예: 16.2 → 11.3) 백지 재작성은 중단하고 Reviser 정밀 수정으로 이월.
            # 문장 분할/병합 표적 수정이 sl 조준에는 백지 재작성보다 정확하다.
            if not sl_ok:
                sl_side = "over" if self._sl_over(avg_sl, sl_range) else "under"
                if prev_sl_side and sl_side != prev_sl_side:
                    self._log(
                        f"[{self.AGENT_LABEL}] sl 진동 감지 ({prev_sl_side}→{sl_side}, "
                        f"평균 {avg_sl:.1f} / 목표 {sl_range}) — Writer 재작성 중단, "
                        f"Reviser 정밀 수정으로 이월"
                    )
                    break
                prev_sl_side = sl_side
            else:
                prev_sl_side = None
            attempt += 1
            self._cancel_check()

            notes: list[str] = []
            failing_now: set[str] = set()
            if not plagiarism_report.passed:
                # hard 축(표절·날조)만 재작성 사유로 — soft(출처 커버리지 등)는
                # 재작성으로 해소 불가능하므로 Writer에게 먹이지 않는다 (예산 낭비 차단)
                hard_keys = (list(getattr(plagiarism_report, "plag_fails", []))
                             + list(getattr(plagiarism_report, "fab_fails", [])))
                failed_items = "\n".join(
                    f"- {key}: {plagiarism_report.checklist.get(key, {}).get('note', '')}"
                    for key in hard_keys
                )
                self._log(f"[{self.AGENT_LABEL}] 표절/날조 위험 감지 — 재작성 {attempt}/{max_retries}회")
                for key in hard_keys:
                    note = plagiarism_report.checklist.get(key, {}).get("note", "")
                    self._log(f"[{self.AGENT_LABEL}]   ⤷ 걸린 항목: {key} — {note[:120]}")
                if plagiarism_report.notes:
                    self._log(f"[{self.AGENT_LABEL}]   ⤷ 비고: {plagiarism_report.notes[:120]}")
                notes.append(
                    f"The previous version failed these plagiarism/fabrication checks:\n{failed_items}\n"
                    f"Fix each failed item specifically. Use stronger paraphrasing and "
                    f"original sentence structure; remove or honestly attribute any "
                    f"invented quotes, names, or figures."
                )
                if getattr(plagiarism_report, "fab_fails", []):
                    failing_now.add("날조")
                    carry["날조"] = (
                        "An earlier attempt was flagged for fabrication — do NOT introduce "
                        "any direct quotes, named experts, statistics, or dates that are "
                        "not present in the sources."
                    )
                if getattr(plagiarism_report, "plag_fails", []):
                    failing_now.add("표절")
                    carry["표절"] = (
                        "An earlier attempt was flagged for source-similar phrasing — keep "
                        "every sentence fully original in wording and structure."
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
                failing_now.add("단어수")
                carry["단어수"] = f"Keep the word count within {wc_range} words."
            if not sl_ok:
                self._log(
                    f"[{self.AGENT_LABEL}] 평균 문장 길이 {avg_sl:.1f}단어 목표({sl_range}) 벗어남 "
                    f"— 재작성 {attempt}/{max_retries}회"
                )
                direction = "shorter, simpler sentences" if avg_sl > 0 and self._sl_over(avg_sl, sl_range) else "slightly longer, fuller sentences"
                _mid_hint = sl_aim_hint(sl_range, level.value)
                notes.append(
                    f"The article's AVERAGE sentence length is {avg_sl:.1f} words, which is OUTSIDE "
                    f"the required range of {sl_range}. Rewrite using {direction} so the average "
                    f"falls WITHIN {sl_range} — aim for {_mid_hint}. "
                    f"Also keep the word count within {wc_range} words. "
                    f"Keep the facts and fully original wording."
                )
                self._log(f"[{self.AGENT_LABEL}] sl 재작성 조준점: {_mid_hint}")
                failing_now.add("문장길이")
                carry["문장길이"] = (
                    f"Keep the AVERAGE sentence length within {sl_range} — aim for {_mid_hint}."
                )
            if cefr_result and not cefr_result.passed:
                self._log(
                    f"[{self.AGENT_LABEL}] CEFR 난이도 위반 — 재작성 {attempt}/{max_retries}회"
                )
                for v in cefr_result.violations:
                    self._log(f"[{self.AGENT_LABEL}]   ⤷ {v}")
                notes.append(cefr_feedback(cefr_result))
                failing_now.add("CEFR")
                carry["CEFR"] = "Keep vocabulary and sentence structure at the target CEFR level."

            # 승계 경고 병기 — 이번에 통과했어도 과거에 걸린 게이트의 제약을 되새긴다
            carried = [msg for gate, msg in carry.items() if gate not in failing_now]
            if carried:
                notes.append(
                    "[Standing constraints from earlier attempts — still mandatory, "
                    "do NOT reintroduce these issues]\n"
                    + "\n".join(f"- {m}" for m in carried)
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
                # 직전 시도가 인용 0으로 확정됐으면 무출처 가드레일 삽입 (선제 날조 차단)
                force_no_source_guard=not article.sources,
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
                force_no_source_guard=not article.sources,
            )
            # 수정 후 표절 재검사 원칙 유지
            plagiarism_report = self._plagcheck.run(article)
            fact_passed, issues = self._factcheck.run(article, real_sources)
            if not fact_passed:
                self._log(
                    f"[{self.AGENT_LABEL}] 사실 점검 의심 항목 잔류 — "
                    f"미리보기에서 확인 후 AI 수정 채팅으로 보완해주세요"
                )

        # ── Step 3.5: 게이트 미충족 잔존 시 Reviser 정밀 수정 (최대 2회) ──
        # Writer 3회로 못 맞춘 것을 승인 전에 지시 기반으로 고친다 —
        # Phase 2에서는 본문을 절대 바꾸지 않으므로, 자동 수정은 여기가 마지막.
        writer_rewrites = attempt  # 게이트 루프 재작성 횟수 (사실점검 재작성은 별도)
        unmet = self._measure_gates(
            article, plagiarism_report, wc_range, sl_range, cefr_key, level
        )
        reviser_attempts = 0
        if unmet:
            article, plagiarism_report, reviser_attempts, unmet = self._refine_with_reviser(
                article, plagiarism_report, level, sub_level,
                wc_range, sl_range, cefr_key, unmet, writer_rewrites,
            )

        # ── Phase 1 종료 시점 미충족 게이트·수정 이력 기록 ─────────────────
        # Agent5가 거부 사유의 출처를 구분하는 근거:
        #   여기 기록됨   → "Phase 1 재작성 소진 후 미충족 상태로 진입"
        #   여기 없음     → "Phase 2 재측정에서 이탈" (미리보기 채팅 수정 등)
        article.phase1_unmet = [g for g, _ in unmet]
        article.revision_history = (
            f"Writer {writer_rewrites}회 + Reviser {reviser_attempts}회 수정 거침"
            if (writer_rewrites or reviser_attempts) else ""
        )
        if unmet:
            self._log(
                f"[{self.AGENT_LABEL}] ❌ 미충족 게이트 잔존({', '.join(g for g, _ in unmet)}) — "
                f"미리보기에서 AI 수정 채팅으로 해결해주세요"
            )

        # ── 출처 0건 관측 — 원인(검색 문제 vs Writer 과판정) 진단은 파이프라인 밖
        #    Claude 세션 몫이므로, 그대로 복사해 물어볼 문의문을 로그에 남긴다 ──
        if not article.sources:
            available = [s for s in real_sources if s.get("url")]
            self._log(
                f"[{self.AGENT_LABEL}] ⚠️ 출처 0건 — 이 기사는 사실 점검(출처 대조)이 "
                f"생략된 채 생성됐습니다. 아래 문의문을 복사해 Claude에게 진단을 요청하세요."
            )
            self._log("───── 문의문 시작 (여기부터 복사) ─────")
            self._log(
                f'news-pipeline5에서 출처 0건 기사가 나왔어. '
                f'토픽: "{topic[:80]}" / 매체: {level.value}'
            )
            if available:
                self._log(
                    f"SourceFinder는 출처 {len(available)}건을 찾았는데 "
                    f"Writer가 전부 '주제와 무관' 판정으로 제외했어:"
                )
                for i, s in enumerate(available, 1):
                    self._log(f"  {i}. {(s.get('title') or '?')[:60]} — {s.get('url')}")
                self._log(
                    "위 출처 목록과 기사 토픽을 대조해서 (a) 검색이 무관한 출처를 "
                    "가져온 건지 (b) Writer 판정이 과하게 깐깐한 건지 판정하고, "
                    "문제인 쪽(source_finder 검색 정확도 또는 writer의 SOURCE RELEVANCE "
                    "기준)을 고쳐줘."
                )
            else:
                self._log("SourceFinder 검색 단계에서부터 출처가 0건이었어 (Writer 판정 이전 문제).")
                self._log(
                    "검색 질의가 토픽과 어긋났는지, web_search 호출이 실패(400 등)했는지 "
                    "위쪽 [SourceFinder] 로그를 보고 원인을 찾아서 고쳐줘."
                )
            self._log("───── 문의문 끝 (여기까지 복사) ─────")

        return article, plagiarism_report

    # ------------------------------------------------------------------
    # Phase 1 게이트 측정·Reviser 정밀 수정
    # ------------------------------------------------------------------

    def _measure_gates(
        self, article, plagiarism_report, wc_range: str, sl_range: str, cefr_key, level,
    ) -> list[tuple[str, str]]:
        """hard 게이트를 재측정해 미충족 목록을 반환한다.

        반환: [(게이트명, "[게이트] 측정값 / 허용범위 — 표적 지시"), ...]
        지시문은 Reviser REVISION REQUEST에 그대로 들어간다.
        """
        from agents.sub_agents.utils import sl_aim_hint
        unmet: list[tuple[str, str]] = []

        wc = article.word_count
        if not self._writer._word_count_in_range(wc, wc_range):
            _nums = re.findall(r"\d+", wc_range)
            over = bool(_nums) and wc > int(_nums[-1])
            action = ("trim redundant phrases and minor details"
                      if over else "expand with relevant, factual detail")
            unmet.append(("단어수", f"[단어수] {wc}단어 / 허용 {wc_range} — {action} to fall within {wc_range} words"))

        avg_sl = self._writer._avg_sentence_length(article.text)
        if not self._writer._sentence_length_in_range(avg_sl, sl_range):
            action = ("split the 2-3 longest sentences"
                      if self._sl_over(avg_sl, sl_range) else "combine short, choppy sentences")
            unmet.append((
                "문장길이",
                f"[문장길이] 평균 {avg_sl:.1f}단어 / 허용 {sl_range} — {action}; "
                f"aim for {sl_aim_hint(sl_range, level.value)}",
            ))

        if cefr_key is not None:
            from agents.sub_agents.cefr_checker import validate as _cefr_validate
            from agents.sub_agents.article_classifier import classify as _classify
            _cls = _classify(article.text, cefr_key)
            if not _cls.skip_cefr:
                _cv = _cefr_validate(article.text, cefr_key)
                if _cv is not None and not _cv.passed:
                    unmet.append((
                        "CEFR",
                        f"[CEFR] {'; '.join(_cv.violations[:2])} — simplify vocabulary and "
                        f"sentence structure to the target level",
                    ))

        # hard 두 축만 게이트 — soft(출처 커버리지)는 여기서 잡지 않는다
        plag = list(getattr(plagiarism_report, "plag_fails", []))
        fab = list(getattr(plagiarism_report, "fab_fails", []))
        if plag:
            unmet.append((
                "표절",
                f"[표절] 유사성 경고 {len(plag)}건 ({', '.join(plag[:3])}) — rephrase the "
                f"flagged passages in fully original wording",
            ))
        if fab:
            # "9_fabrication 실패" 같은 판정명은 Reviser가 실행할 수 없다 —
            # 걸린 인용문 원문을 지시에 넣어 "이 문장을 삭제/간접화하라"로 번역한다.
            fab_notes = " · ".join(
                plagiarism_report.checklist.get(k, {}).get("note", "")[:150]
                for k in fab if plagiarism_report.checklist.get(k, {}).get("note")
            )
            quotes = self._quoted_spans(article.text)
            if quotes:
                qlist = " / ".join(f'"{q[:120]}"' for q in quotes[:3])
                action = (
                    f"delete these direct quotes or convert them to INDIRECT statements "
                    f"without quotation marks: {qlist}. Do NOT add any new quotes, "
                    f"named experts, or unsourced figures"
                )
            else:
                action = (
                    "remove the invented detail/attribution described above, or replace it "
                    "with honest unquoted vague attribution (e.g. 'some researchers say'). "
                    "Do NOT add any new quotes or unsourced figures"
                )
            unmet.append((
                "날조",
                f"[날조] {', '.join(fab)}"
                + (f" — checker note: {fab_notes}" if fab_notes else "")
                + f" — {action}",
            ))
        return unmet

    @staticmethod
    def _quoted_spans(text: str) -> list[str]:
        """본문에서 직접 인용(따옴표 안 문장)을 추출한다 — 날조 지시 번역용."""
        spans = []
        for a, b in re.findall(r'"([^"]{8,200})"|“([^”]{8,200})”', text):
            spans.append((a or b).strip())
        return spans

    def _refine_with_reviser(
        self, article, plagiarism_report, level, sub_level: str,
        wc_range: str, sl_range: str, cefr_key, unmet: list, writer_rewrites: int,
        max_attempts: int = 2,
    ):
        """게이트 미충족 잔존분을 Reviser로 정밀 수정한다 (최대 2회).

        본문이 바뀌면 표절 재검사. 반환: (article, plagiarism_report, 시도횟수, 최종 unmet)
        """
        from agents.sub_agents.reviser import ReviserAgent
        reviser = ReviserAgent(log_callback=self._log)
        attempts = 0
        while unmet and attempts < max_attempts:
            attempts += 1
            self._cancel_check()
            self._log(
                f"[{self.AGENT_LABEL}] 게이트 미충족 잔존 — Reviser 정밀 수정 "
                f"{attempts}/{max_attempts}회 ({', '.join(g for g, _ in unmet)})"
            )
            reasons = "\n".join(line for _, line in unmet)
            instruction = (
                f"REVISION REQUEST: The article failed these hard gates after "
                f"{writer_rewrites} Writer rewrites. Fix EVERY item below — this is "
                f"the top priority and is non-negotiable:\n{reasons}\n\n"
                f"While fixing, keep the facts, sources, and reading level. "
                f"Output the full revised article."
            )
            article2, _reply, changed = reviser.run(
                article, instruction, level,
                plagiarism_report=plagiarism_report, sub_level=sub_level,
            )
            if not changed:
                self._log(f"[{self.AGENT_LABEL}] Reviser가 본문을 수정하지 않음 — 정밀 수정 중단")
                break
            article = article2
            plagiarism_report = self._plagcheck.run(article)  # 수정 후 표절 재검사 원칙
            unmet = self._measure_gates(
                article, plagiarism_report, wc_range, sl_range, cefr_key, level
            )
        if attempts:
            self._log(
                f"[{self.AGENT_LABEL}] Reviser 정밀 수정 종료 — "
                f"{'게이트 전부 충족 ✓' if not unmet else '미충족 잔존: ' + ', '.join(g for g, _ in unmet)}"
            )
        return article, plagiarism_report, attempts, unmet

    def produce_extras(
        self, topic: str, level: Level, section: Section, article, plagiarism_report,
        sub_level: str = "L2",
    ) -> ContentPackage:
        """Phase 2 — 교정 제안 + 크로스워드 + 워크북을 수행하고 패키지를 완성한다.

        Phase 1 미리보기에서 승인한 본문은 여기서 절대 바꾸지 않는다 —
        승인본 = 최종본. Editor는 제안만 하고(원 설계), 반영 여부는 사람이 정한다.
        """
        # ── Step 3: 교정 제안 (본문 반영 안 함) ──────────────────────
        editing_suggestions = self._editor.run(article, level)
        if editing_suggestions:
            self._log(
                f"[{self.AGENT_LABEL}] 교정 제안 {len(editing_suggestions)}건 — "
                f"반영 안 함 (승인 본문 유지, 결과 화면에서 확인)"
            )

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

    def get_skip_stats(self) -> dict[str, int]:
        """이 인스턴스가 CEFR 게이트를 건너뛴 횟수 반환 (BRIEF / DIALOGUE 키)."""
        return dict(self._skip_stats)

    @staticmethod
    def _sl_over(avg: float, range_str: str) -> bool:
        """평균 문장 길이가 목표 범위 상한을 초과하면 True (재작성 방향 결정용)."""
        try:
            nums = re.findall(r"\d+", range_str)
            return avg > int(nums[1])
        except (ValueError, IndexError, TypeError):
            return False

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

