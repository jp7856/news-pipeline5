"""전 매체 발행연도 분포 — 아카이브 오염 확인용. EXCLUDE 변경 없음."""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")
import openpyxl

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"
_YEAR_RE  = re.compile(r"\b(20\d{2}|19\d{2})\b")

SHEETS = ["KINDER", "KIDS", "JUNIOR", "TIMES", "JUNIOR M"]

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)

for sheet_name in SHEETS:
    ws   = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    hdr  = [str(c).strip() if c else "" for c in rows[0]]

    dt_c  = next((i for i,h in enumerate(hdr) if "날짜"  in h or "date"  in h.lower()), None)
    iss_c = next((i for i,h in enumerate(hdr) if "호수"  in h or "issue" in h.lower()), None)

    year_cnt: dict[int, int] = {}
    no_date = 0

    for row in rows[1:]:
        if not row: continue
        yr = None
        if dt_c is not None and len(row) > dt_c and row[dt_c]:
            m = _YEAR_RE.search(str(row[dt_c]))
            if m: yr = int(m.group())
        if yr is None:
            no_date += 1
            continue
        year_cnt[yr] = year_cnt.get(yr, 0) + 1

    total = sum(year_cnt.values())
    old   = sum(v for y,v in year_cnt.items() if y <= 2010)
    mid   = sum(v for y,v in year_cnt.items() if 2011 <= y <= 2021)
    new   = sum(v for y,v in year_cnt.items() if y >= 2022)

    print(f"\n{'='*60}")
    print(f"{sheet_name}  (총 {total}건 + 날짜없음 {no_date}건)")
    print(f"  ~2010: {old}건  /  2011~2021: {mid}건  /  2022~: {new}건")
    print(f"{'연도':>6}  {'건수':>6}")
    print(f"{'─'*16}")
    for yr in sorted(year_cnt.keys()):
        marker = " ◀ 2011공백확인" if yr in (2010, 2011, 2012) else ""
        print(f"  {yr:>4}  {year_cnt[yr]:>6}{marker}")
    if no_date:
        print(f"  {'(없음)':>4}  {no_date:>6}")
