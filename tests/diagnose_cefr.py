"""basic.xlsx — 레벨별 탈락 원인 분해 + avg_min 재보정 제안.
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

all_buckets: dict[str, list] = {}
all_texts:   dict[str, list[str]] = {}

for sheet_name in ["KINDER", "KIDS", "JUNIOR", "TIMES", "JUNIOR M"]:
    ws   = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    hdr  = [str(c).strip() if c else "" for c in rows[0]]
    lv_col = next((i for i,h in enumerate(hdr) if "레벨" in h or "level" in h.lower()), None)
    tx_col = next((i for i,h in enumerate(hdr) if "본문" in h or "text" in h.lower()), None)
    if lv_col is None or tx_col is None: continue
    for row in rows[1:]:
        if not row or len(row) <= max(lv_col, tx_col): continue
        lv  = str(row[lv_col]).strip() if row[lv_col] else ""
        txt = str(row[tx_col]).strip() if row[tx_col] else ""
        if not lv or len(txt) < 50: continue
        num = re.search(r"\d+", lv)
        if not num: continue
        key = f"{PREFIX[sheet_name]}_L{num.group()}"
        if key not in LEVELS: continue
        all_buckets.setdefault(key, []).append(validate(txt, key))
        all_texts.setdefault(key, []).append(txt)

# ── 탈락 원인 분해 ─────────────────────────────────────────────────────
print(f"{'레벨키':<14} {'n':>4}  {'통과':>4}  "
      f"{'too_easy':>8} {'avg↑':>5} {'maxlen↑':>7} {'clauses↑':>8} {'FK↑':>4}")
print("─" * 65)
for key in sorted(all_buckets):
    results = all_buckets[key]
    n = len(results)
    passed    = sum(1 for r in results if r.passed)
    too_easy  = sum(1 for r in results if r.too_easy)
    avg_over  = sum(1 for r in results if any("평균 문장 길이" in v and "초과" in v for v in r.violations))
    max_over  = sum(1 for r in results if any("최장 문장" in v for v in r.violations))
    cl_over   = sum(1 for r in results if any("절" in v for v in r.violations))
    fk_over   = sum(1 for r in results if any("FK" in v for v in r.violations))
    print(f"{key:<14} {n:>4}  {passed/n*100:>3.0f}%  "
          f"{too_easy:>7}건 {avg_over:>4}건 {max_over:>6}건 {cl_over:>7}건 {fk_over:>3}건")

# ── avg_min 재보정 제안 ────────────────────────────────────────────────
print()
print(f"{'레벨키':<14}  {'avg_min 현행':>11}  {'실측 p10':>8}  {'제안값':>7}")
print("─" * 50)
for key in sorted(all_buckets):
    results = all_buckets[key]
    avgs = [r.avg_sentence_len for r in results]
    p10  = pct(avgs, 10)
    spec = LEVELS[key]
    suggest = max(1.0, round(p10 * 2) / 2)   # 0.5 단위 내림
    flag = " ← 수정 필요" if spec.avg_min > p10 else ""
    print(f"{key:<14}  {spec.avg_min:>11.1f}  {p10:>8.1f}  {suggest:>7.1f}{flag}")
