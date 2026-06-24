import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import openpyxl
from agents.sub_agents.cefr_checker import validate

wb = openpyxl.load_workbook(r"C:\Users\jp\Desktop\basic.xlsx", read_only=True, data_only=True)
ws = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr = [str(c).strip() if c else "" for c in rows[0]]
lv_col = next(i for i,h in enumerate(hdr) if "레벨" in h or "level" in h.lower())
tx_col = next(i for i,h in enumerate(hdr) if "본문" in h or "text" in h.lower())

candidates = []
for row in rows[1:]:
    if not row or len(row) <= max(lv_col, tx_col): continue
    lv  = str(row[lv_col]).strip() if row[lv_col] else ""
    txt = str(row[tx_col]).strip() if row[tx_col] else ""
    if lv != "LEVEL 1" or len(txt) < 50: continue
    r  = validate(txt, "TIMES_L1")
    wc = len(re.findall(r"[A-Za-z']+", txt))
    if 13.0 <= r.avg_sentence_len <= 19.0 and r.passed and 110 <= wc <= 150:
        candidates.append((r, wc, txt))

candidates.sort(key=lambda c: c[0].fk_grade)

# #8 (idx 7) — 중간, #20 (idx 19) — 높은 FK
for label, idx in [("#8 (FK 중간)", 7), ("#20 (FK 높음)", 19)]:
    if idx >= len(candidates): continue
    r, wc, txt = candidates[idx]
    print(f"[{label}] avg={r.avg_sentence_len} FK={r.fk_grade} wc={wc}")
    print(txt)
    print()
