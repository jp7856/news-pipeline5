"""TIMES_L2 avg_min 통과 + FK 최저 10건 전문."""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import textstat, openpyxl
from agents.sub_agents.cefr_checker import validate
from agents.sub_agents.article_classifier import classify

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"
EXCLUDE_SECTIONS = {
    "Photo News", "Briefs", "Star Brief", "News in Brief",
    "Cartoon", "Did You Know", "Did You Know?", "Debating", "Cover", "Q & A",
    "NE You",
    "My Journal", "Book Review",
    "Stories", "Story",
    "Readings for Junior", "VoA Broadcast News",
}
AVG_MIN = 13.5

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
lv_col = next(i for i,h in enumerate(hdr) if "레벨" in h or "level"   in h.lower())
tx_col = next(i for i,h in enumerate(hdr) if "본문" in h or "text"    in h.lower())
sc_col = next(i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower())

suspects = []
for row in rows[1:]:
    if not row or len(row) <= max(lv_col, tx_col, sc_col): continue
    lv  = str(row[lv_col]).strip() if row[lv_col] else ""
    txt = str(row[tx_col]).strip() if row[tx_col] else ""
    sec = str(row[sc_col]).strip() if row[sc_col] else ""
    if not lv or len(txt) < 50: continue
    if sec in EXCLUDE_SECTIONS: continue
    wc = len(re.findall(r"[A-Za-z']+", txt))
    if wc < 100: continue
    m = re.search(r"\d+", lv)
    if not m or f"TIMES_L{m.group()}" != "TIMES_L2": continue
    if classify(txt, "TIMES_L2").skip_cefr: continue
    avg = validate(txt, "TIMES_L2").avg_sentence_len
    if avg < AVG_MIN: continue
    fk = textstat.flesch_kincaid_grade(txt)
    if fk >= 8.0: continue
    suspects.append((fk, avg, sec, txt))

suspects.sort(key=lambda x: x[0])  # FK 오름차순

print(f"TIMES_L2 avg_min({AVG_MIN}) 통과 + FK < 8.0 전체 {len(suspects)}건 중 최저 FK 10건\n")

for i, (fk, avg, sec, txt) in enumerate(suspects[:10], 1):
    wc = len(re.findall(r"[A-Za-z']+", txt))
    print("=" * 72)
    print(f"[{i}]  섹션: {sec}  |  avg={avg:.1f}  FK={fk:.1f}  wc={wc}")
    print("=" * 72)
    print(txt)
    print()
