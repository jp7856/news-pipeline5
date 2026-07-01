"""EditorAgent — 기사의 문법·적합성·어색함을 검토하고 수정 제안 목록을 반환한다.
직접 수정하지 않고, 제안만 제공한다."""

import logging
from typing import Callable

import anthropic

from config import CLAUDE_MODEL, SYSTEM_PROMPT, LEVEL_CONFIG
from models import ArticleResult, EditingSuggestion, Level
from agents.sub_agents.utils import call_claude_json

logger = logging.getLogger(__name__)


class EditorAgent:
    def __init__(
        self,
        client: anthropic.Anthropic,
        log_callback: Callable[[str], None] | None = None,
    ):
        self._client = client
        self._log = log_callback or (lambda msg: logger.info(msg))

    def run(self, article: ArticleResult, level: Level) -> list[EditingSuggestion]:
        self._log("[Editor] 교정 시작")
        cfg = LEVEL_CONFIG[level.value]

        prompt = f"""You are editing an article for {cfg['newspaper']} (CEFR {cfg['cefr']}, target: {cfg['target']}).

Review the article below for:
1. Grammar errors
2. Suitability for the target age group and CEFR level (vocabulary too hard/easy, sentence complexity)
3. Awkward phrasing or unnatural expressions
4. Factual or logical flow issues

Rules:
- Do NOT rewrite or apply changes.
- Only list sentences or passages that need improvement.
- Skip anything that is already correct.
- For each issue, quote the exact original passage and provide a suggested revision.

Article:
\"\"\"
{article.text}
\"\"\"

Respond in this exact JSON format:
{{
  "suggestions": [
    {{
      "original": "exact quote from the article",
      "suggestion": "your proposed revision",
      "reason": "brief reason"
    }}
  ]
}}

If there are no issues, return: {{"suggestions": []}}"""

        try:
            data = self._call_claude(prompt)
        except ValueError as e:
            self._log(f"[Editor] 응답 처리 실패 — 교정 없이 진행: {e}")
            data = {"suggestions": []}

        suggestions = [
            EditingSuggestion(
                original=s.get("original", ""),
                suggestion=s.get("suggestion", ""),
                reason=s.get("reason", ""),
            )
            for s in data.get("suggestions", [])
        ]

        self._log(f"[Editor] 완료 — 수정 제안 {len(suggestions)}건")
        return suggestions

    def _call_claude(self, prompt: str) -> dict:
        return call_claude_json(
            self._client, self._log, "Editor",
            model=CLAUDE_MODEL, max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        )
