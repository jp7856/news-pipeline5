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
    "Readings for Junior","VoA Broadcast News","Think About It","My Diary","Pros & Cons",
}
_SE = re.compile(r"(?<=[.!?])\s+")
def avg_sl(t):
    p=[len(re.findall(r"[A-Za-z']+",s)) for s in _SE.split(t.strip())]
    p=[w for w in p if w>=1]; return sum(p)/len(p) if p else 0.0

wb=openpyxl.load_workbook(XLSX,read_only=True,data_only=True)
ws=wb["TIMES"]; rows=list(ws.iter_rows(values_only=True))
hdr=[str(c).strip() if c else "" for c in rows[0]]
lv=next(i for i,h in enumerate(hdr) if "level" in h.lower() or "레벨" in h)
tx=next(i for i,h in enumerate(hdr) if "text"  in h.lower() or "본문" in h)
sc=next((i for i,h in enumerate(hdr) if "section" in h.lower() or "섹션" in h),None)

band=[]
for row in rows[1:]:
    if not row or len(row)<=max(lv,tx): continue
    lval=str(row[lv]).strip() if row[lv] else ""
    txt =str(row[tx]).strip() if row[tx] else ""
    sec =str(row[sc]).strip() if (sc and row[sc]) else ""
    if not lval or len(txt)<50 or sec in EXCL: continue
    if len(re.findall(r"[A-Za-z']+",txt))<100: continue
    m=re.search(r"\d+",lval)
    if not m or m.group()!="1": continue
    cls=classify(txt,"TIMES_L1")
    if cls.skip_cefr: continue
    a=avg_sl(txt)
    if 6.5<=a<8.5:
        band.append((a,cls.article_type.value,sec,txt))

band.sort(key=lambda x:x[0])
n=len(band); step=(n-1)/9
picks=[band[round(step*i)] for i in range(10)]
for a,fmt,sec,txt in picks:
    print(f"[{a:.3f}] | {fmt} | {sec} | {txt[:120].replace(chr(10),' ')}")
