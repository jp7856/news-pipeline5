"""에이전트 1-1 ~ 1-5 분리 검증 — 라우팅·지침 로딩·프롬프트 주입."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import Level
from config import LEVEL_CONFIG
from agents.level_agents import AGENT1_BY_LEVEL, create_agent1
from agents.content_producer import ContentProducerAgent, GUIDELINES_DIR
from agents.sub_agents.writer import WriterAgent
from agents.translator import _LEVEL_STYLE

# 1) 5개 레벨 모두 라우팅 등록 + LEVEL_CONFIG/번역 스타일 존재
assert len(AGENT1_BY_LEVEL) == 5
for lv in Level:
    assert lv in AGENT1_BY_LEVEL, f"{lv} 라우팅 누락"
    assert lv.value in LEVEL_CONFIG, f"{lv.value} LEVEL_CONFIG 누락"
    assert lv.value in _LEVEL_STYLE, f"{lv.value} 번역 스타일 누락"
print("routing OK")

# 2) 에이전트 라벨·지침 파일 매핑
expected = {
    Level.KINDER: ("Agent1-1 KINDER", "agent1_1_kinder.md"),
    Level.KIDS: ("Agent1-2 KIDS", "agent1_2_kids.md"),
    Level.JUNIOR: ("Agent1-3 JUNIOR", "agent1_3_junior.md"),
    Level.TIMES: ("Agent1-4 TIMES", "agent1_4_times.md"),
    Level.JUNIOR_M: ("Agent1-5 JUNIOR M", "agent1_5_junior_m.md"),
}
for lv, (label, fname) in expected.items():
    cls = AGENT1_BY_LEVEL[lv]
    assert cls.AGENT_LABEL == label, (cls.AGENT_LABEL, label)
    assert cls.GUIDELINE_FILE == fname
    assert (GUIDELINES_DIR / fname).exists(), f"{fname} 파일 없음"
print("labels & files OK")

# 3) 지침 로딩 — 실측 지침이 입고된 4개 매체는 로드, placeholder(JUNIOR M)는 빈 문자열
for lv in (Level.KINDER, Level.KIDS, Level.JUNIOR, Level.TIMES):
    agent = create_agent1(lv)
    assert agent._guidelines, f"{lv.value} 지침이 비어 있음"
    assert "Sub-level" in agent._guidelines and "<!--" not in agent._guidelines
agent_m = create_agent1(Level.JUNIOR_M)
assert agent_m._guidelines == "", "JUNIOR M은 placeholder여야 함"
print("guideline content OK / placeholder skip OK")

# 4) 지침 본문이 있으면 로드되고 주석은 제거됨
test_md = GUIDELINES_DIR / "_test_tmp.md"
test_md.write_text("<!-- 메모: 주입 금지 -->\n제목은 항상 의문문으로.\n", encoding="utf-8")
try:
    class _TmpAgent(ContentProducerAgent):
        GUIDELINE_FILE = "_test_tmp.md"
    tmp = _TmpAgent.__new__(_TmpAgent)
    tmp._log = lambda m: None
    loaded = tmp._load_guidelines()
    assert loaded == "제목은 항상 의문문으로.", repr(loaded)
finally:
    test_md.unlink()
print("guideline load OK")

# 5) Writer 프롬프트 주입 헬퍼
cfg = LEVEL_CONFIG["junior"]
assert WriterAgent._guideline_hint("", cfg) == ""
hint = WriterAgent._guideline_hint("제목은 의문문", cfg)
assert "NE Times Junior" in hint and "제목은 의문문" in hint
print("prompt injection OK")

# 6) 서브레벨 사양 — 구성 완전성 + Writer 병합·폴백
from config import SUBLEVEL_CONFIG

for lv in Level:
    subs = SUBLEVEL_CONFIG[lv.value]
    assert "L1" in subs and "L2" in subs, f"{lv.value} 서브레벨 누락"
    for spec in subs.values():
        assert {"cefr", "word_count_range", "sentence_length", "paragraph_count"} <= set(spec)
assert "L3" not in SUBLEVEL_CONFIG["kinder"], "KINDER는 L1~L2만"

cfg, sub = WriterAgent._merge_config(Level.KIDS, "L3")
assert sub == "L3" and cfg["cefr"] == "A2+" and cfg["word_count_range"] == "155–180"
assert cfg["newspaper"] == "NE Times Kids"  # 베이스 값 유지
cfg, sub = WriterAgent._merge_config(Level.KINDER, "L3")  # 없는 서브레벨 → L2 폴백
assert sub == "L2" and cfg["cefr"] == "A1"
print("sublevel config & merge OK")

# 7) 워드카운트 범위 판정 (로그 사양 라인용)
assert WriterAgent._word_count_in_range(170, "150–190") is True
assert WriterAgent._word_count_in_range(149, "150–190") is False
assert WriterAgent._word_count_in_range(191, "150–190") is False
assert WriterAgent._word_count_in_range(100, "이상한값") is True  # 파싱 불가 시 경고 안 함
print("word count range check OK")

# 8) 시트 컬럼 — 서브레벨 컬럼 추가 후에도 상태·비용 위치 불변
from agents.worksheet import SHEET_COLUMNS, STATUS_COL, COST_COL
assert len(SHEET_COLUMNS) == 18 and SHEET_COLUMNS[17] == "서브레벨"
assert STATUS_COL == 16 and COST_COL == 17
print("sheet columns OK")

print("ALL TESTS PASSED")
