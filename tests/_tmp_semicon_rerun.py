"""(b) 반도체 L2 재실행 — railway 자격증명으로 실제 시트 기록까지 확인."""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = sys.stdout
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")
from models import Level, Section
from orchestrator import Orchestrator
from agents.worksheet import WorksheetAgent, SHEET_COLUMNS

orc = Orchestrator(log_callback=print)
state = orc.run_phase1(topic="Global semiconductor supply chains and export controls",
                       level=Level.TIMES, section=Section.ECONOMY, sub_level="L2")
package, _ = orc.run_phase2(state)
plag = state["plagiarism_report"]
rv = package.review_result
print(f"\n[b] 표절축 passed={plag.passed} plag={plag.plag_fails} fab={plag.fab_fails}")
print(f"    soft: {plag.soft_warnings[:120] if plag.soft_warnings else '(없음)'}")
print(f"    검수: passed={rv.passed} status={rv.status.value}")
print(f"    warnings: {rv.warnings[:200] if rv.warnings else '(없음)'}")

ws = WorksheetAgent()
last = ws._get_sheet().get_all_values()[-1]
print(f"\n[시트 실기록] 상태={last[15]} 표절검사={last[10]}")
print(f"  검수경고 컬럼: {last[18][:150] if len(last)>18 else '(없음)'}")
