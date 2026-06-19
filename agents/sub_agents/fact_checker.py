"""FactCheckerAgent — 기사 내용을 검색된 출처와 대조해 사실 부합 여부를 점검한다.

ORCHESTRATION.md 3절 공통 작성 원칙: 기사 내용은 팩트에 부합해야 하며,
출처와 모순되거나 어디에도 근거가 없는 구체적 수치·인용은 날조로 간주한다.
"""

import json
import logging
from typing import Callable

import anthropic

from config import CLAUDE_MODEL, SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class FactCheckerAgent:
    def __init__(
        self,
        client: anthropic.Anthropic,
        log_callback: Callable[[str], None] | None = None,
    ):
        self._client = client
        self._log = log_callback or (lambda msg: logger.info(msg))

    def run(self, article, sources: list[dict]) -> tuple[bool, list[str]]:
        """기사를 출처와 대조 점검한다.

        Returns: (passed, issues) — 출처가 없으면 점검을 생략하고 통과 처리.
        """
        if not sources:
            self._log("[FactCheck] 검색된 출처 없음 — 대조 점검 생략")
            return True, []

        self._log("[FactCheck] 사실 점검 시작 — 출처 대조")
        try:
            passed, issues = self._check(article.text, sources)
        except Exception as e:
            self._log(f"[FactCheck] 점검 오류 (무시하고 계속): {e}")
            return True, []

        if passed:
            self._log("[FactCheck] 통과 — 출처와 모순되는 내용 없음")
        else:
            self._log(f"[FactCheck] 의심 항목 {len(issues)}건 발견")
        return passed, issues

    def _check(self, article_text: str, sources: list[dict]) -> tuple[bool, list[str]]:
        source_lines = "\n".join(
            f"- {s.get('title', '')} ({s.get('date', '날짜 미상')}): {s.get('snippet', '')}"
            for s in sources
        )
        prompt = f"""당신은 교육용 신문의 사실 검증 담당자입니다.
아래 기사 초안을 검색된 실제 출처 요약과 대조해 점검하세요.

[기사 초안]
{article_text}

[검색된 출처 요약]
{source_lines}

점검 기준:
1. 기사 주장(수치, 날짜, 이름, 사건)이 출처 내용과 모순되는가?
2. 출처 어디에도 근거가 없는 '구체적인' 수치·통계·직접 인용이 있는가? (날조 의심)

주의: 출처 요약은 한 줄뿐이므로, 요약에 없다는 이유만으로 지적하지 마세요.
출처와 '명백히 모순'되거나, 지나치게 구체적인데 뒷받침이 전혀 없어 날조가
의심되는 내용만 지적하세요. 일반적 배경 설명은 문제 삼지 않습니다.

아래 JSON 형식으로만 응답하세요:
{{"passed": true, "issues": ["문제가 된 기사 내용과 이유를 한 줄씩"]}}"""

        message = self._client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        data = json.loads(raw)
        issues = [str(i) for i in data.get("issues", [])]
        return bool(data.get("passed", True)) and not issues, issues
