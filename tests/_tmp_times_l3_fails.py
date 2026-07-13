import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")
import openpyxl
from agents.sub_agents.cefr_checker import LEVELS
from agents.sub_agents.article_classifier import classify

XLSX = r"C:\Users\jp\Desktop\기사\articles.xlsx"
EXCL = {
    "Photo News","Briefs","Star Brief","News in Brief","Cartoon",
    "Did You Know","Did You Know?","Debating","Cover","Q & A","NE You",
    "My Journal","Book Review","Stories","Story",
    "Readings for Junior","VoA Broadcast News","Think About It","My Diary",
}
_SE      = re.compile(r"(?<=[.!?])\s+")
_YEAR_RE = re.compile(r"\b(20\d{2})\b")

def avg_sl(t):
    p = [len(re.findall(r"[A-Za-z']+", s)) for s in _SE.split(t.strip())]
    p = [w for w in p if w >= 1]
    return sum(p) / len(p) if p else 0.0

wb   = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
ws   = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
lv_c = next(i for i,h in enumerate(hdr) if "레벨" in h or "level"   in h.lower())
tx_c = next(i for i,h in enumerate(hdr) if "본문" in h or "text"    in h.lower())
sc_c = next((i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower()), None)
dt_c = next((i for i,h in enumerate(hdr) if "날짜" in h or "date"    in h.lower()), None)

AVG_MIN = LEVELS["TIMES_L3"].avg_min  # 15.5
fails = []

for row in rows[1:]:
    if not row or len(row) <= max(lv_c, tx_c): continue
    lval = str(row[lv_c]).strip() if row[lv_c] else ""
    txt  = str(row[tx_c]).strip() if row[tx_c] else ""
    sec  = str(row[sc_c]).strip() if (sc_c and row[sc_c]) else ""
    if not lval or len(txt) < 50 or sec in EXCL: continue
    if len(re.findall(r"[A-Za-z']+", txt)) < 100: continue
    m = re.search(r"\d+", lval)
    if not m or m.group() != "3": continue
    # 레벨 시트 확인 (TIMES_L3)
    from agents.sub_agents.cefr_checker import LEVELS
    if "TIMES_L3" not in LEVELS: continue
    cls = classify(txt, "TIMES_L3")
    if cls.skip_cefr: continue
    a = avg_sl(txt)
    if a < 1.0: continue
    # 연도 필터: 2024~
    yr = None
    if dt_c is not None and len(row) > dt_c and row[dt_c]:
        ym = _YEAR_RE.search(str(row[dt_c]))
        if ym: yr = int(ym.group())
    if yr is not None and yr < 2024: continue
    if a < AVG_MIN:
        fails.append((a, cls.article_type.value, sec, txt))

fails.sort(key=lambda x: x[0])
picks = fails[:15] if len(fails) > 15 else fails
print(f"TIMES_L3 2024~ 탈락 전체 {len(fails)}건 / 출력 {len(picks)}개  (avg_min={AVG_MIN})\n")
for a, fmt, sec, txt in picks:
    preview = txt[:150].replace("\n", " ")
    print(f"[{a:.3f}] | {fmt} | {sec} | {preview}")
