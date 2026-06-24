"""cefr_checker + cefr_key_for 통합 테스트 — API 호출 없음."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from models import Level
from agents.level_agents import cefr_key_for
from agents.sub_agents.cefr_checker import validate, LEVELS

# ── 1. cefr_key_for 키 변환 전수 검사 ────────────────────────────────
print("=== 1. cefr_key_for() 전체 레벨/서브레벨 ===")
combos = [
    (Level.KINDER,   "L1"), (Level.KINDER,   "L2"),
    (Level.KIDS,     "L1"), (Level.KIDS,     "L2"), (Level.KIDS,     "L3"),
    (Level.JUNIOR,   "L1"), (Level.JUNIOR,   "L2"), (Level.JUNIOR,   "L3"),
    (Level.JUNIOR_M, "L1"), (Level.JUNIOR_M, "L2"),
    (Level.TIMES,    "L1"), (Level.TIMES,    "L2"), (Level.TIMES,    "L3"),
]
key_errors = []
for level, sub in combos:
    key = cefr_key_for(level, sub)
    exists = key in LEVELS if key else False
    ok = key is not None and exists
    if not ok:
        key_errors.append((level.value, sub, key))
    print(f"  {'OK ' if ok else 'ERR'} {level.value:10s} {sub} -> {str(key):15s}  in LEVELS={exists}")
print(f"  => {'전체 통과' if not key_errors else f'실패 {len(key_errors)}건: {key_errors}'}")

# ── 2. None/미등록 반환 엣지케이스 ───────────────────────────────────
print()
print("=== 2. None 반환 엣지케이스 ===")
for level, sub, expect_none in [
    (Level.KINDER, "",    True),   # 빈 sub_level
    (Level.KINDER, "l1", False),   # 소문자 (LEVELS에 없음 → exists=False)
    (Level.KINDER, "L4", False),   # 없는 레벨 (LEVELS에 없음)
]:
    key = cefr_key_for(level, sub)
    exists = key in LEVELS if key else False
    print(f"  sub={sub!r:5s} -> key={str(key):15s}  None={key is None}  exists={exists}")

# ── 3. validate() 샘플 5개 ────────────────────────────────────────────
print()
print("=== 3. validate() 샘플 테스트 ===")
SAMPLES = [
    # (설명, level, sub_level, 텍스트, 기대 통과 여부)
    (
        "KINDER_L1 적정",
        Level.KINDER, "L1",
        "The sun is very hot today. Animals need water to stay cool. "
        "Dogs drink from a bowl. Birds drink from a pond. Stay safe in summer heat.",
        True,
    ),
    (
        "KINDER_L1 너무 어려움",
        Level.KINDER, "L1",
        "The proliferation of surveillance infrastructure raises substantial concerns "
        "among civil liberties advocates who contend that existing regulatory frameworks "
        "struggle to keep pace with the rapid expansion of camera networks.",
        False,
    ),
    (
        "JUNIOR_L2 적정",
        Level.JUNIOR, "L2",
        # avg 12-16 목표: 각 문장 13-18단어, 절 최대 2개, FK ≤8.5
        "Scientists discovered a new species of fish near the Pacific Ocean floor. "
        "The fish lives more than 3,000 meters below the surface, where there is no light. "
        "Without any light, the creature cannot develop eyes and must locate food another way. "
        "Researchers believe the discovery helps explain how animals adjust to extreme environments. "
        "A follow-up study is planned for next year to examine the fish's feeding habits more closely.",
        True,
    ),
    (
        "TIMES_L2 복잡한 문장 (FAIL 예상)",
        Level.TIMES, "L2",
        "South Korea operates one of the highest concentrations of surveillance cameras in Asia, "
        "with millions of units installed across streets, public transport, schools, and government "
        "buildings nationwide, a trend that privacy advocates say is accelerating faster than "
        "existing legal frameworks can adequately regulate or monitor.",
        False,
    ),
    (
        "JUNIOR_M_L1 적정 범위",
        Level.JUNIOR_M, "L1",
        # avg 11-15 목표: 절 최대 2개(and/that/if 조합 주의), FK ≤8.5
        "Artificial intelligence is changing the way people use computers and phones. "
        "In recent years, AI tools have become common in everyday life. "
        "Companies now use AI to recommend movies, translate languages, and spot diseases early. "
        "Some experts, however, warn about the risks of careless AI development. "
        "Governments around the world are writing new rules to keep AI development safe.",
        True,
    ),
]

all_match = True
for desc, level, sub, text, expect_pass in SAMPLES:
    key = cefr_key_for(level, sub)
    result = validate(text, key)
    match = result.passed == expect_pass
    if not match:
        all_match = False
    icon = "OK " if match else "ERR"
    pf = "PASS" if result.passed else "FAIL"
    viols = " | ".join(result.violations) if result.violations else "-"
    print(f"  [{icon}] {desc}")
    print(f"        key={key}  {pf}(expect={'PASS' if expect_pass else 'FAIL'})  "
          f"avg={result.avg_sentence_len}  max={result.max_sentence_len}  "
          f"cl={result.max_clauses}  fk={result.fk_grade}")
    if result.violations:
        for v in result.violations:
            print(f"        위반: {v}")

print()
print(f"=== 최종: {'전체 통과' if (not key_errors and all_match) else '실패 항목 있음'} ===")
