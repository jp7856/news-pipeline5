"""Agent 2: 번역 — Agent 1이 생성한 영어 기사를 레벨별 한국어로 번역한다.

레벨별 번역 스타일:
  kinder : 유치~초등저학년, 아주 쉬운 단어, 짧은 문장
  kids   : 초등고학년~중등, 교과서 수준 어휘
  junior : 중등, 표준 뉴스 기사체
  times  : 고등이상, 신문 격식체
"""

import logging
from typing import Callable

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, SYSTEM_PROMPT
from models import ContentPackage

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# 레벨별 번역 지침
# ------------------------------------------------------------------
_LEVEL_STYLE: dict[str, str] = {
    "kinder": (
        "독자: 유치원~초등 저학년 (6~9세)\n"
        "- 아주 쉬운 단어만 사용. 한자어·외래어 최소화.\n"
        "- 한 문장은 15단어 이내로 짧게.\n"
        "- 어려운 개념은 '~(이)란 ~이에요' 형식으로 풀어쓰기.\n"
        "- summary_ko: 2문장으로 요약."
    ),
    "kids": (
        "독자: 초등 고학년~중학교 1학년 (10~13세)\n"
        "- 중학 교과서 수준 어휘.\n"
        "- 전문 용어는 괄호로 간단히 설명.\n"
        "- summary_ko: 3문장으로 요약."
    ),
    "junior": (
        "독자: 중학생 (13~16세)\n"
        "- 표준 한국어. 뉴스 기사체.\n"
        "- 전문 용어 그대로 사용.\n"
        "- summary_ko: 3문장으로 요약."
    ),
    "times": (
        "독자: 고등학생 이상 (16세+)\n"
        "- 격식체 한국어. 신문 기사 문체.\n"
        "- 전문 용어·수치 정확히 유지.\n"
        "- summary_ko: 4문장으로 요약."
    ),
}

_TRANSLATOR_SYSTEM = (
    "당신은 영어 교육 신문 기사를 한국어로 번역하는 전문 에디터입니다.\n"
    "지정된 마커 형식으로만 출력하세요. JSON이나 마크다운 코드 블록을 사용하지 마세요.\n"
    "번역은 원문의 사실과 뉘앙스를 정확히 유지하되, 지정된 독자 수준에 맞게 작성하세요."
)


class TranslatorAgent:
    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        log_callback: Callable[[str], None] | None = None,
    ):
        self._log = log_callback or (lambda msg: logger.info(msg))
        from agents.sub_agents.usage_tracker import TrackedClient
        self._client = client or TrackedClient(api_key=ANTHROPIC_API_KEY)

    def run(self, package: ContentPackage) -> ContentPackage:
        """영어 기사를 한국어로 번역하고 ContentPackage에 결과를 추가한다."""
        self._log(f"[Agent2] 번역 시작 — [{package.level.value}]")

        try:
            result = self._translate(package)
            package.article.text_ko = result.get("text_ko", "")
            package.article.summary_ko = result.get("summary_ko", "")
            self._log(f"[Agent2] 완료 — 번역 {len(package.article.text_ko)}자 / 요약 완료")
        except Exception as e:
            self._log(f"[Agent2] 오류: {e}")
            package.article.text_ko = ""
            package.article.summary_ko = ""

        return package

    # ------------------------------------------------------------------

    def _translate(self, package: ContentPackage) -> dict:
        level_str = package.level.value
        style = _LEVEL_STYLE.get(level_str, _LEVEL_STYLE["junior"])

        prompt = (
            f"[번역 레벨: {level_str}]\n"
            f"{style}\n\n"
            f"아래 영어 기사를 한국어로 번역하세요.\n\n"
            f"--- 기사 ---\n{package.article.text}\n--- 끝 ---\n\n"
            f"아래 마커 형식 그대로 응답하세요. 다른 텍스트는 출력하지 마세요:\n\n"
            f"<번역>\n"
            f"한국어 번역 전체 본문\n"
            f"</번역>\n"
            f"<요약>\n"
            f"한국어 요약 (레벨에 맞는 문장 수, 반드시 완결된 문장으로 끝낼 것)\n"
            f"</요약>"
        )

        message = self._client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=8192,
            system=[
                {
                    "type": "text",
                    "text": _TRANSLATOR_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": prompt}],
        )
        if message.stop_reason == "max_tokens":
            self._log("[Agent2] 경고: 출력이 토큰 한도에서 잘렸습니다")
        return self._parse_markers(message.content[0].text)

    @staticmethod
    def _parse_markers(raw: str) -> dict:
        """<번역>...</번역> <요약>...</요약> 마커에서 텍스트를 추출한다."""
        import re

        def extract(tag: str) -> str:
            m = re.search(rf"<{tag}>\s*(.*?)\s*</{tag}>", raw, re.DOTALL)
            if m:
                return m.group(1).strip()
            # 닫는 마커가 없으면 여는 마커 이후 전체 (다음 마커 전까지)
            m = re.search(rf"<{tag}>\s*(.*?)(?=<|\Z)", raw, re.DOTALL)
            return m.group(1).strip() if m else ""

        return {
            "text_ko": extract("번역"),
            "summary_ko": extract("요약"),
        }
