"""reviser sl 조준점 이식 검증 — TIMES L1 (21.0->11.4 과잉교정 재현 조건).

확인: Phase2 Reviser가 sl 거부를 받을 때 조준점 지시를 받고,
      최종 sl이 하한을 뚫지 않고 범위(13-18) 안에 안착하는지.

실행: python test_reviser_sl_aim.py
"""
import re
import sys
import os
import io

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))

from models import Level, Section
from orchestrator import Orchestrator
from agents.sub_agents.writer import WriterAgent

TOPIC = "The James Webb Space Telescope and its discoveries about the early universe"
SECTION = Section.SCIENCE


def _in_range(val, range_str):
    try:
        nums = re.findall(r"\d+", range_str)
        return float(nums[0]) <= val <= float(nums[1])
    except Exception:
        return None


logs = []


def capture(msg):
    logs.append(msg)
    print(msg)


print(f"\n{'=' * 72}")
print(f"  TIMES L1  |  {TOPIC[:52]}")
print(f"{'=' * 72}")

package = None
try:
    orc = Orchestrator(log_callback=capture)
    state = orc.run_phase1(topic=TOPIC, level=Level.TIMES, section=SECTION, sub_level="L1")
    package, _ = orc.run_phase2(state)
except Exception as e:
    if any(k in str(e).lower() for k in ("sheet", "google", "credentials", "gspread")):
        print(f"\n[INFO] Sheets 저장 실패 (로컬 미설정) — 이전 단계 기준 분석")
    else:
        print(f"\n[ERROR] {e}")
        import traceback; traceback.print_exc()

print(f"\n{'─' * 62}")
print("[RESULT] TIMES L1 — sl 조준점 이식 검증")

# ── 조준점 지시가 실제로 들어갔는지 ──────────────────────────────────
aim_logs = [l.strip() for l in logs if "sentence-length issue specifically" in l or "around" in l and "REVISION" not in l]
reviser_input_logs = [l.strip() for l in logs if l.startswith("[Reviser] 입력")]

# ── Phase2 회차별 sl 추적 ─────────────────────────────────────────
p2_events = []
for l in logs:
    m_rej = re.search(r"\[Phase2\] 검수 거부 — 재작성 (\d+)/(\d+)회.*사유: (.+)", l)
    if m_rej:
        p2_events.append(("reject", m_rej.group(1), m_rej.group(3)[:80]))
    m_fixed = re.search(r"\[Reviser\] 수정 완료 — (\d+)단어", l)
    if m_fixed:
        p2_events.append(("rewrote", int(m_fixed.group(1)), None))
    if "[Reviser] 답변만 제공" in l:
        p2_events.append(("answer_only", None, None))

print("\n[Phase2 Reviser 회차별 이벤트]")
for t, a, b in p2_events:
    if t == "reject":
        print(f"    거부 {a}회 — {b}")
    elif t == "rewrote":
        print(f"      -> Reviser 재작성: {a}단어")
    elif t == "answer_only":
        print(f"      -> ⚠ 답변만 제공")

if package:
    final_wc = package.article.word_count
    final_sl = WriterAgent._avg_sentence_length(package.article.text)
    _cfg, _ = WriterAgent._merge_config(Level.TIMES, "L1")
    wc_range = _cfg.get("word_count_range", "")
    sl_range = _cfg.get("sentence_length", "")
    sl_ok = _in_range(final_sl, sl_range)
    passed = bool(package.review_result and package.review_result.passed)

    print(f"\n[최종 상태]")
    print(f"    wc = {final_wc} (목표 {wc_range})")
    print(f"    sl = {final_sl:.1f} (목표 {sl_range}) {'✓ 범위 내 안착' if sl_ok else '⚠ 여전히 이탈'}")
    print(f"    Agent5 최종: {'✅ 승인' if passed else '❌ 거부'}")
    if not passed and package.review_result:
        print(f"    거부 사유: {package.review_result.notes[:150]}")

from agents.sub_agents.usage_tracker import usage_cost
cost = usage_cost()
print(f"\n    비용: ${cost['usd']:.4f} ({cost['krw']:,}원)")
print(f"{'─' * 62}")
