"""ReviserAgent — 에디터(사용자)와 대화하며 기사 초안을 수정한다.

Phase 1 미리보기 화면에서:
  - 수정 지시("두 번째 문단 쉽게") → 기사를 고치고 무엇을 바꿨는지 답변
  - 질문("표절 경고 왜 떴어?")     → 기사는 그대로 두고 답변만
"""

import logging
import re
from typing import Callable

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, SYSTEM_PROMPT, LEVEL_CONFIG
from models import ArticleResult, Level, PlagiarismReport

logger = logging.getLogger(__name__)


class ReviserAgent:
    def __init__(self, log_callback: Callable[[str], None] | None = None):
        self._log = log_callback or (lambda msg: logger.info(msg))
        from agents.sub_agents.usage_tracker import TrackedClient
        self._client = TrackedClient(api_key=ANTHROPIC_API_KEY)

    def run(
        self,
        article: ArticleResult,
        instruction: str,
        level: Level,
        plagiarism_report: PlagiarismReport | None = None,
        history: list[dict] | None = None,
    ) -> tuple[ArticleResult, str, bool]:
        """에디터 입력을 처리한다.

        Returns: (article, reply, changed)
          - reply   : 에디터에게 보여줄 한국어 답변
          - changed : 기사가 수정됐는지 여부
        """
        self._log(f"[Reviser] 입력 — \"{instruction[:60]}\"")
        cfg = LEVEL_CONFIG[level.value]

        plag_context = ""
        if plagiarism_report is not None:
            items = "\n".join(
                f"  - {k}: {'통과' if v.get('pass') else '실패'} — {v.get('note', '')}"
                for k, v in plagiarism_report.checklist.items()
            )
            plag_context = (
                f"\n\n[표절 검사 결과: {'통과' if plagiarism_report.passed else '경고'}]\n"
                f"{items}\n"
                f"비고: {plagiarism_report.notes or '없음'}"
            )

        history_text = ""
        if history:
            lines = []
            for h in history[-6:]:
                lines.append(f"에디터: {h['user']}")
                lines.append(f"AI: {h['assistant']}")
            history_text = "\n\n[이전 대화]\n" + "\n".join(lines)

        prompt = f"""You are assisting a human editor reviewing a draft article for \
{cfg['newspaper']} (CEFR {cfg['cefr']}, target: {cfg['target']}, \
{cfg['word_count_range']} words).

--- CURRENT DRAFT ---
{article.text}
--- END DRAFT ---{plag_context}{history_text}

The editor says (may be in Korean):
"{instruction}"

Decide what the editor wants:
1. If it is a REVISION REQUEST — rewrite the article applying it (keep CEFR level, \
word count range, topic) and briefly explain in Korean what you changed.
2. If it is a QUESTION or comment — answer it in Korean. Do NOT rewrite the article.

Respond in this exact format:
<reply>
한국어 답변 (질문이면 답변, 수정이면 무엇을 어떻게 바꿨는지 1~3문장)
</reply>
<article>
revised article text — ONLY include this block if you actually changed the article. \
Omit the entire block if the article should stay the same.
</article>"""

        message = self._client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text

        m_reply = re.search(r"<reply>\s*(.*?)\s*</reply>", raw, re.DOTALL)
        reply = m_reply.group(1).strip() if m_reply else raw.strip()

        m_article = re.search(r"<article>\s*(.*?)\s*</article>", raw, re.DOTALL)
        changed = False
        if m_article:
            new_text = m_article.group(1).strip()
            if new_text and new_text != article.text:
                article.text = new_text
                article.word_count = len(new_text.split())
                changed = True

        if changed:
            self._log(f"[Reviser] 수정 완료 — {article.word_count}단어")
        else:
            self._log("[Reviser] 답변만 제공 (기사 변경 없음)")

        return article, reply, changed
