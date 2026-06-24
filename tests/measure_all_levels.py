"""basic.xlsx 전체 — 레벨별 4개 지표 p90 실측 + validate() 통과율.
API 호출 없음.
"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import openpyxl
from agents.sub_agents.cefr_checker import validate, LEVELS

XLSX_PATH = r"C:\Users\jp\Desktop\basic.xlsx"

PREFIX = {"KINDER":"KINDER","KIDS":"KIDS","JUNIOR":"JUNIOR","TIMES":"TIMES","JUNIOR M":"JUNIORM"}

def pct(xs, p):
    s = sorted(xs)
    return s[min(int(len(s)*p/100), len(s)-1)]

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)

print("=" * 100)
print(f"{'레벨키':<14} {'n':>4}  "
      f"{'avg p50':>7}{'avg p90':>8}  "
      f"{'maxlen p50':>10}{'maxlen p90':>11}  "
      f"{'cl p90':>6}  "
      f"{'FK p50':>6}{'FK p90':>7}  "
      f"{'통과율':>6}")
print("=" * 100)

all_buckets = {}

for sheet_name in ["KINDER", "KIDS", "JUNIOR", "TIMES", "JUNIOR M"]:
    ws   = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    hdr  = [str(c).strip() if c else "" for c in rows[0]]
    lv_col = next((i for i,h in enumerate(hdr) if "레벨" in h or "level" in h.lower()), None)
    tx_col = next((i for i,h in enumerate(hdr) if "본문" in h or "text" in h.lower()), None)
    if lv_col is None or tx_col is None:
        continue

    for row in rows[1:]:
        if not row or len(row) <= max(lv_col, tx_col): continue
        lv  = str(row[lv_col]).strip() if row[lv_col] else ""
        txt = str(row[tx_col]).strip() if row[tx_col] else ""
        if not lv or len(txt) < 50: continue
        num = re.search(r"\d+", lv)
        if not num: continue
        key = f"{PREFIX[sheet_name]}_L{num.group()}"
        if key not in LEVELS: continue
        result = validate(txt, key)
        all_buckets.setdefault(key, []).append(result)

for key in sorted(all_buckets):
    results = all_buckets[key]
    n = len(results)
    avgs  = [r.avg_sentence_len for r in results]
    mxs   = [r.max_sentence_len for r in results]
    cls_  = [r.max_clauses      for r in results]
    fks   = [r.fk_grade         for r in results]
    passed = sum(1 for r in results if r.passed)
    spec   = LEVELS[key]

    print(f"{key:<14} {n:>4}  "
          f"{pct(avgs,50):>7.1f}{pct(avgs,90):>8.1f}  "
          f"{pct(mxs,50):>10}{pct(mxs,90):>11}  "
          f"{pct(cls_,90):>6}  "
          f"{pct(fks,50):>6.1f}{pct(fks,90):>7.1f}  "
          f"{passed/n*100:>5.0f}%")

print("=" * 100)
print()

# ── 현행 LEVELS 설정과 p90 비교 ──────────────────────────────────────────
print(f"{'레벨키':<14}  {'avg_max 현행':>11} {'→ p90':>7}  "
      f"{'maxlen 현행':>10} {'→ p90':>7}  "
      f"{'clauses 현행':>11} {'→ p90':>6}  "
      f"{'fk_max 현행':>10} {'→ p90':>7}")
print("-" * 100)
for key in sorted(all_buckets):
    results = all_buckets[key]
    avgs = [r.avg_sentence_len for r in results]
    mxs  = [r.max_sentence_len for r in results]
    cls_ = [r.max_clauses      for r in results]
    fks  = [r.fk_grade         for r in results]
    spec = LEVELS[key]
    print(f"{key:<14}  {spec.avg_max:>11.0f} {pct(avgs,90):>7.1f}  "
          f"{spec.max_sentence_len:>10} {pct(mxs,90):>7}  "
          f"{spec.max_clauses:>11} {pct(cls_,90):>6}  "
          f"{spec.fk_max:>10.1f} {pct(fks,90):>7.1f}")
