import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")
import openpyxl
from agents.sub_agents.cefr_checker import LEVELS
from agents.sub_agents.article_classifier import classify

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"
EXCLUDE_SECTIONS = {
    "Photo News","Briefs","Star Brief","News in Brief","Cartoon",
    "Did You Know","Did You Know?","Debating","Cover","Q & A","NE You",
    "My Journal","Book Review","Stories","Story","Readings for Junior",
    "VoA Broadcast News","Think About It","My Diary",
}
_SE = re.compile(r"(?<=[.!?])\s+")

def avg_sl(t):
    p = [len(re.findall(r"[A-Za-z']+", s)) for s in _SE.split(t.strip())]
    p = [w for w in p if w >= 1]
    return sum(p) / len(p) if p else 0.0

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
lv_col = next(i for i,h in enumerate(hdr) if "level" in h.lower() or "레벨" in h)
tx_col = next(i for i,h in enumerate(hdr) if "text"  in h.lower() or "본문" in h)
sc_col = next((i for i,h in enumerate(hdr) if "section" in h.lower() or "섹션" in h), None)

fails = []
for row in rows[1:]:
    if not row or len(row) <= max(lv_col, tx_col): continue
    lval = str(row[lv_col]).strip() if row[lv_col] else ""
    txt  = str(row[tx_col]).strip() if row[tx_col] else ""
    sec  = str(row[sc_col]).strip() if (sc_col and row[sc_col]) else ""
    if not lval or len(txt) < 50 or sec in EXCLUDE_SECTIONS: continue
    if len(re.findall(r"[A-Za-z']+", txt)) < 100: continue
    m = re.search(r"\d+", lval)
    if not m or m.group() != "1": continue
    cls = classify(txt, "TIMES_L1")
    if cls.skip_cefr: continue
    a = avg_sl(txt)
    if a < 1.0 or a >= 10.5: continue
    fails.append((a, cls.article_type.value, sec, txt))

fails.sort(key=lambda x: x[0])
n = len(fails)
picks = [fails[0], fails[1], fails[n//2 - 1], fails[n//2], fails[-2], fails[-1]]

for a, fmt, sec, txt in picks:
    preview = txt[:150].replace("\n", " ")
    print(f"[{a:.3f}] | {fmt} | {sec} | {preview}")
