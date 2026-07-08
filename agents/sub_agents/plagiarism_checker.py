"""PlagiarismCheckerAgent — 8개 항목 체크리스트로 표절 위험을 검사한다."""

import logging
from typing import Callable

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, SYSTEM_PROMPT
from models import ArticleResult, PlagiarismReport
from agents.sub_agents.utils import parse_json

logger = logging.getLogger(__name__)

CHECKLIST_PROMPT = """Run the following Plagiarism-Risk Checklist on the article below.

{checklist}

Article to check:
\"\"\"
{article}
\"\"\"

Sources used:
{sources}

For each of the 9 categories, mark whether it PASSES or FAILS, and briefly explain why.
Then give an overall verdict.

Respond in this exact JSON format:
{{
  "passed": true or false,
  "checklist": {{
    "1_sentence_paraphrasing": {{"pass": true/false, "note": "..."}},
    "2_vocabulary_independence": {{"pass": true/false, "note": "..."}},
    "3_information_compression": {{"pass": true/false, "note": "..."}},
    "4_structural_originality": {{"pass": true/false, "note": "..."}},
    "5_quotation_safety": {{"pass": true/false, "note": "..."}},
    "6_tone_purpose_shift": {{"pass": true/false, "note": "..."}},
    "7_source_transparency": {{"pass": true/false, "note": "..."}},
    "8_final_safety_check": {{"pass": true/false, "note": "..."}},
    "9_fabrication": {{"pass": true/false, "note": "..."}}
  }},
  "notes": "Overall summary and any red flags"
}}"""

CHECKLIST_TEXT = """1. Sentence-Level Paraphrasing
   - No sentence copies the structure of a source sentence
   - No distinctive phrases from the source are reused
   - Verbs, connectors, and sentence order are reworked

2. Vocabulary Independence
   - Key words are factual (names, places), not stylistic
   - Descriptive language is original
   - No "signature expressions" from the source appear unchanged

3. Information Selection & Compression
   - Only essential facts included
   - Long source explanations are summarized
   - Facts are not presented in the same order as the source

4. Structural Originality
   - Paragraph order differs from the source
   - Content follows an educational outline, not a news flow
   - Headings (if any) are original

5. Quotation Safety
   - Quotes are short and necessary
   - Quotes are clearly attributed
   - No long quotes replacing paraphrasing

6. Tone & Purpose Shift
   - Tone is neutral and explanatory
   - Language fits the student's CEFR level
   - Article serves an educational purpose, not news reproduction

7. Source Transparency (coverage assessment — informational)
   - Are the listed sources sufficient to back the article's main claims?
   - This is a COVERAGE judgment, not a fabrication check — writing from
     general knowledge with few sources is acceptable for this newspaper.

8. Final Safety Check
   - "If I removed the sources, would this still read like my own explanation?"
   - Yes → Safe / No → Revise

9. Fabrication Check
   - No invented details, dates, statistics, or events
   - No quotes or attributed statements assigned to people/institutions that
     cannot be verified (e.g. a named expert who does not appear in any source)
   - Vague-but-honest attribution ("some researchers say") is NOT fabrication;
     inventing a specific person, title, or figure IS"""


class PlagiarismCheckerAgent:
    # hard 축 — passed를 결정
    HARD_PLAGIARISM_ITEMS = (
        "1_sentence_paraphrasing", "2_vocabulary_independence",
        "3_information_compression", "4_structural_originality",
    )
    HARD_FABRICATION_ITEMS = ("5_quotation_safety", "9_fabrication")
    # soft 축 — 검수경고로만
    SOFT_COVERAGE_ITEMS = ("7_source_transparency", "8_final_safety_check")

    def __init__(
        self,
        client: anthropic.Anthropic,
        log_callback: Callable[[str], None] | None = None,
    ):
        self._client = client
        self._log = log_callback or (lambda msg: logger.info(msg))

    def run(self, article: ArticleResult) -> PlagiarismReport:
        self._log("[Plagiarism] 표절 검사 시작")

        prompt = CHECKLIST_PROMPT.format(
            checklist=CHECKLIST_TEXT,
            article=article.text,
            sources="\n".join(article.sources) if article.sources else "No sources provided",
        )

        data = self._call_claude(prompt)

        checklist = data.get("checklist", {})
        fails = {k: v for k, v in checklist.items() if not v.get("pass", True)}

        # hard 두 축(표절·날조)만 passed를 결정. soft(6·7·8)는 경고로만.
        # LLM의 overall passed는 무시 — 출처 커버리지를 표절로 합산하던 과민 원인.
        plag_fails = [k for k in fails if k in self.HARD_PLAGIARISM_ITEMS]
        fab_fails = [k for k in fails if k in self.HARD_FABRICATION_ITEMS]
        passed = not (plag_fails or fab_fails)

        soft_parts = []
        cov = [f"{k}: {fails[k].get('note', '')[:100]}" for k in self.SOFT_COVERAGE_ITEMS if k in fails]
        if cov:
            soft_parts.append("⚠ 출처 커버리지: " + " · ".join(cov))
        if "6_tone_purpose_shift" in fails:
            soft_parts.append(f"⚠ 문체·목적: {fails['6_tone_purpose_shift'].get('note', '')[:100]}")
        soft_warnings = chr(10).join(soft_parts)

        if passed:
            tail = f" (soft 경고 {len(soft_parts)}건 — 검수경고로 기록)" if soft_parts else ""
            self._log(f"[Plagiarism] 통과 ✓{tail}")
        else:
            axes = []
            if plag_fails:
                axes.append(f"표절: {', '.join(plag_fails)}")
            if fab_fails:
                axes.append(f"날조: {', '.join(fab_fails)}")
            self._log(f"[Plagiarism] 경고 — {' / '.join(axes)}")

        return PlagiarismReport(
            passed=passed,
            checklist=checklist,
            notes=data.get("notes", ""),
            plag_fails=plag_fails,
            fab_fails=fab_fails,
            soft_warnings=soft_warnings,
        )

    def _call_claude(self, prompt: str) -> dict:
        message = self._client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        return parse_json(message.content[0].text)
