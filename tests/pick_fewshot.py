"""basic.xlsx에서 few-shot 후보 추출. API 없음.
TIMES L1: avg 13~19, FK ≤ 12.5 (fk_max), 단어수 110~150
"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import openpyxl
from agents.sub_agents.cefr_checker import validate

XLSX_PATH = r"C:\Users\jp\Desktop\basic.xlsx"

TARGET = {"sheet": "TIMES", "level_val": "LEVEL 1", "cefr_key": "TIMES_L1"}

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws   = wb[TARGET["sheet"]]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]

lv_col  = next(i for i,h in enumerate(hdr) if "레벨" in h or "level" in h.lower())
tx_col  = next(i for i,h in enumerate(hdr) if "본문" in h or "text" in h.lower())
ttl_col = next((i for i,h in enumerate(hdr) if "제목" in h or "title" in h.lower()), None)

candidates = []
for row in rows[1:]:
    if not row or len(row) <= max(lv_col, tx_col): continue
    lv  = str(row[lv_col]).strip() if row[lv_col] else ""
    txt = str(row[tx_col]).strip() if row[tx_col] else ""
    ttl = str(row[ttl_col]).strip() if ttl_col and row[ttl_col] else ""
    if lv != TARGET["level_val"] or len(txt) < 50: continue

    r = validate(txt, TARGET["cefr_key"])
    wc = len(re.findall(r"[A-Za-z']+", txt))
    candidates.append((r, wc, ttl, txt))

# avg 13~19, FK 통과, 단어수 110~150 우선 — 조건 완화 순서로 출력
def score(c):
    r, wc, _, _ = c
    in_avg = 13.0 <= r.avg_sentence_len <= 19.0
    in_wc  = 110 <= wc <= 150
    fk_ok  = r.passed  # FK ≤ fk_max
    return (not in_avg, not fk_ok, not in_wc, r.fk_grade)

candidates.sort(key=score)

print(f"{'#':>3}  {'avg':>5}  {'FK':>5}  {'wc':>4}  {'pass':>5}  제목 (앞 60자)")
print("─" * 80)
for i, (r, wc, ttl, txt) in enumerate(candidates[:20], 1):
    in_avg = 13.0 <= r.avg_sentence_len <= 19.0
    flag   = "✓" if (in_avg and r.passed and 110 <= wc <= 150) else " "
    print(f"{i:>3}{flag} {r.avg_sentence_len:>5.1f}  {r.fk_grade:>5.1f}  {wc:>4}  "
          f"{'PASS' if r.passed else 'FAIL':>5}  {ttl[:60] or txt[:60]}")

print()
print("── 조건 완전 충족 기사 본문 (avg 13~19, FK pass, wc 110~150) ──")
shown = 0
for r, wc, ttl, txt in candidates:
    if not (13.0 <= r.avg_sentence_len <= 19.0 and r.passed and 110 <= wc <= 150):
        continue
    shown += 1
    print(f"\n[{shown}] avg={r.avg_sentence_len} FK={r.fk_grade} wc={wc}")
    print(f"제목: {ttl or '(없음)'}")
    print(txt)
    print()
    if shown >= 5:
        break

if shown == 0:
    print("  조건 충족 기사 없음 — avg/wc 범위 완화 필요")
