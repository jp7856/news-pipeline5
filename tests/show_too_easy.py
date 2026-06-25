"""TIMES_L1 too_easy 샘플 10건 — 본문 일부 + avg 출력. API 없음."""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import openpyxl
from agents.sub_agents.cefr_checker import validate, LEVELS

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"

EXCLUDE_SECTIONS = {
    "Photo News", "Briefs", "Star Brief", "News in Brief",
    "Cartoon", "Did You Know", "Did You Know?", "Debating", "Cover",
    "Q & A",  # TIMES 인터뷰 Q&A 포맷(avg 83wc)
    "NE You",
}

wb  = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws  = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
lv_col  = next(i for i,h in enumerate(hdr) if "레벨" in h or "level" in h.lower())
tx_col  = next(i for i,h in enumerate(hdr) if "본문" in h or "text" in h.lower())
sec_col = next(i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower())
ttl_col = next((i for i,h in enumerate(hdr) if "제목" in h or "title" in h.lower()), None)

samples = []
for row in rows[1:]:
    if not row or len(row) <= max(lv_col, tx_col): continue
    lv  = str(row[lv_col]).strip()  if row[lv_col]  else ""
    txt = str(row[tx_col]).strip()  if row[tx_col]  else ""
    sec = str(row[sec_col]).strip() if row[sec_col] else ""
    ttl = str(row[ttl_col]).strip() if (ttl_col and row[ttl_col]) else ""
    if lv != "LEVEL 1" or sec in EXCLUDE_SECTIONS or len(txt) < 50: continue

    r = validate(txt, "TIMES_L1")
    if r.too_easy:
        samples.append((r.avg_sentence_len, sec, ttl, txt))

# avg 오름차순으로 10건 (하한 근처 + 명확하게 짧은 것 고루 보여줌)
samples.sort(key=lambda x: x[0])
step  = max(1, len(samples) // 10)
picks = [samples[i] for i in range(0, min(len(samples), step * 10), step)][:10]

spec = LEVELS["TIMES_L1"]
print(f"TIMES_L1 too_easy 샘플 (avg_min={spec.avg_min}, 전체 {len(samples)}건 중 10건)")
print(f"{'─'*72}")

for i, (avg, sec, ttl, txt) in enumerate(picks, 1):
    preview = txt[:300].replace("\n", " ")
    print(f"\n[{i}] avg={avg:.1f}단어  섹션={sec}")
    print(f"    제목: {ttl[:70] or '(없음)'}")
    print(f"    본문: {preview}{'...' if len(txt) > 300 else ''}")
