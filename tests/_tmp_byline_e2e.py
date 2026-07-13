"""필자 컬럼 E2E — 실제 생성 1건 + 시트 헤더·행·기존 흐름 검증."""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = sys.stdout
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")
from models import Level, Section
from orchestrator import Orchestrator
from agents.worksheet import WorksheetAgent, SHEET_COLUMNS

orc = Orchestrator(log_callback=lambda m: print(m))
state = orc.run_phase1(topic="How bees make honey", level=Level.KINDER,
                       section=Section.SCIENCE, sub_level="L1")
package, sheet_url = orc.run_phase2(state)

print("\n=== 시트 검증 ===")
ws = WorksheetAgent()
sheet = ws._get_sheet()
header = sheet.row_values(1)
print(f"헤더({len(header)}컬럼): ...{header[15:]}")
assert header == SHEET_COLUMNS, f"헤더 불일치: {header}"
last = sheet.get_all_values()[-1]
print(f"마지막 행: 레벨={last[1]} 상태={last[15][:10]} 서브레벨={last[17]} 필자={last[20] if len(last)>20 else '(없음)'}")
assert len(last) > 20 and last[20] == "Leo", "필자 컬럼 기입 실패"

# 기존 행 조회/발행 흐름
hist = ws.load_history()
print(f"load_history: {len(hist)}건 정상 로드 (구버전 행 포함)")
old_rows_ok = all("topic" in h and "result" in h for h in hist)
print(f"기존 행 파싱: {'전부 정상 ✓' if old_rows_ok else '⚠ 문제'}")
print(f"발행 상태 컬럼 인덱스: STATUS_COL={__import__('agents.worksheet', fromlist=['STATUS_COL']).STATUS_COL} (기존 16 유지 확인)")
