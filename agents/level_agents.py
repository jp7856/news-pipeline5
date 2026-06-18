"""에이전트 1-1 ~ 1-5 — 신문(레벨)별 콘텐츠 제작 에이전트.

공통 파이프라인은 ContentProducerAgent에 있고, 각 에이전트는
자기 지침 마크다운(agents/guidelines/*.md)을 Writer 프롬프트에 주입한다.
구성 기준: ORCHESTRATION.md 2절.
"""

import random
from typing import Callable

from config import SUBLEVEL_CONFIG
from models import Level
from agents.content_producer import ContentProducerAgent


def pick_sublevel(level: Level) -> str:
    """매체 기준에 맞는 레벨 범위 안에서 랜덤하게 서브레벨을 배정한다.

    예: KINDER는 L1~L2, KIDS/JUNIOR/TIMES는 L1~L3 중 하나.
    (ORCHESTRATION.md 3절 — 평균/고정값이 아닌 범위 내 작성 원칙)
    """
    keys = list(SUBLEVEL_CONFIG.get(level.value, {}).keys()) or ["L2"]
    return random.choice(keys)


class Agent1_1Kinder(ContentProducerAgent):
    AGENT_LABEL = "Agent1-1 KINDER"
    GUIDELINE_FILE = "agent1_1_kinder.md"


class Agent1_2Kids(ContentProducerAgent):
    AGENT_LABEL = "Agent1-2 KIDS"
    GUIDELINE_FILE = "agent1_2_kids.md"


class Agent1_3Junior(ContentProducerAgent):
    AGENT_LABEL = "Agent1-3 JUNIOR"
    GUIDELINE_FILE = "agent1_3_junior.md"


class Agent1_4Times(ContentProducerAgent):
    AGENT_LABEL = "Agent1-4 TIMES"
    GUIDELINE_FILE = "agent1_4_times.md"


class Agent1_5JuniorM(ContentProducerAgent):
    AGENT_LABEL = "Agent1-5 JUNIOR M"
    GUIDELINE_FILE = "agent1_5_junior_m.md"


AGENT1_BY_LEVEL: dict[Level, type[ContentProducerAgent]] = {
    Level.KINDER: Agent1_1Kinder,
    Level.KIDS: Agent1_2Kids,
    Level.JUNIOR: Agent1_3Junior,
    Level.TIMES: Agent1_4Times,
    Level.JUNIOR_M: Agent1_5JuniorM,
}


def create_agent1(
    level: Level,
    log_callback: Callable[[str], None] | None = None,
    cancel_check: Callable[[], None] | None = None,
) -> ContentProducerAgent:
    """레벨에 맞는 에이전트 1-X를 생성한다 (미등록 레벨은 공통 베이스로 폴백)."""
    cls = AGENT1_BY_LEVEL.get(level, ContentProducerAgent)
    return cls(log_callback=log_callback, cancel_check=cancel_check)


def guideline_file_for_level(level: Level) -> str | None:
    """레벨에 해당하는 지침 마크다운 파일명을 반환한다 (검수 에이전트가 사용)."""
    cls = AGENT1_BY_LEVEL.get(level)
    return getattr(cls, "GUIDELINE_FILE", None)
