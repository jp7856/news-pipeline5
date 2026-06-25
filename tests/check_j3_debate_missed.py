"""JUNIOR_L3 Debate 미감지 10건 포맷 확인."""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl
from agents.sub_agents.article_classifier import classify, ArticleType, _count_heading_speakers

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"

wb   = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws   = wb["JUNIOR"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
lv_col = next(i for i,h in enumerate(hdr) if "레벨" in h or "level"   in h.lower())
tx_col = next(i for i,h in enumerate(hdr) if "본문" in h or "text"    in h.lower())
sc_col = next(i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower())

missed = []
for row in rows[1:]:
    if not row or len(row) <= max(lv_col, tx_col): continue
    lv  = str(row[lv_col]).strip() if row[lv_col] else ""
    txt = str(row[tx_col]).strip() if row[tx_col] else ""
    sec = str(row[sc_col]).strip() if row[sc_col] else ""
    if lv != "LEVEL 3" or sec != "Debate": continue
    wc = len(re.findall(r"[A-Za-z']+", txt))
    if wc < 80: continue
    r = classify(txt, "JUNIOR_L3")
    if r.article_type != ArticleType.DIALOGUE:
        missed.append(txt)

print(f"미감지 {len(missed)}건 — 본문 전체 출력")
for i, txt in enumerate(missed[:10], 1):
    lines = txt.splitlines()
    cnt, ex = _count_heading_speakers(lines)
    print(f"\n{'='*60}")
    print(f"[{i}] heading_count={cnt}")
    print(txt[:600].replace("\n", "\n  "))
    if len(txt) > 600:
        print(f"  ...[+{len(txt)-600}자]")
