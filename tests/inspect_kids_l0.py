"""KIDS 시트 LEVEL 0 행 메타데이터 전체 출력."""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import openpyxl

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws = wb["KIDS"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]

# 헤더 전체 출력
print("=== 헤더 컬럼 목록 ===")
for i, h in enumerate(hdr):
    print(f"  [{i}] {h!r}")
print()

# 레벨 컬럼 찾기
lv_col  = next(i for i,h in enumerate(hdr) if "레벨" in h or "level" in h.lower())
tx_col  = next(i for i,h in enumerate(hdr) if "본문" in h or "text"  in h.lower())

# LEVEL 0 행 수집
l0_rows = []
for row in rows[1:]:
    if not row: continue
    lv = str(row[lv_col]).strip() if row[lv_col] else ""
    if re.search(r"0", lv) and not re.search(r"[1-9]", lv):  # "0" or "LEVEL 0" 계열
        l0_rows.append(row)

print(f"LEVEL 0 행 총 {len(l0_rows)}건 — 10건 샘플\n")

import random; random.seed(7)
sample = random.sample(l0_rows, min(10, len(l0_rows)))

for i, row in enumerate(sample, 1):
    txt = str(row[tx_col]).strip() if row[tx_col] else ""
    preview = txt[:300].replace("\n", " ")

    print(f"{'='*70}")
    print(f"[{i}]")
    # 본문 외 모든 컬럼 출력
    for ci, (col_name, val) in enumerate(zip(hdr, row)):
        if ci == tx_col:
            continue  # 본문은 별도 출력
        if val is None or str(val).strip() == "":
            continue
        print(f"  {col_name or f'col{ci}'}: {str(val).strip()[:120]}")
    print(f"  본문: {preview}{'...' if len(txt)>300 else ''}")
    print()
