"""geo_template 패턴 디버그 — 2024~ World Tour L3 탈락 기사 전수."""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")
import openpyxl
from agents.sub_agents.article_classifier import _GEO_OPENING, _GEO_MARKERS, _FIRST_SENT_END, _GEO_MARKER_MIN

XLSX = r"C:\Users\jp\Desktop\기사\articles.xlsx"
_SE  = re.compile(r"(?<=[.!?])\s+")
_YR  = re.compile(r"\b(20\d{2})\b")
AVG_MIN = 11.5

def avg_sl(t):
    p = [len(re.findall(r"[A-Za-z']+", s)) for s in _SE.split(t.strip())]
    p = [w for w in p if w >= 1]
    return sum(p)/len(p) if p else 0.0

wb   = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
ws   = wb["JUNIOR"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
lv_c = next(i for i,h in enumerate(hdr) if "레벨" in h or "level" in h.lower())
tx_c = next(i for i,h in enumerate(hdr) if "본문" in h or "text" in h.lower())
sc_c = next((i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower()), None)
dt_c = next((i for i,h in enumerate(hdr) if "날짜" in h or "date" in h.lower()), None)

results = []  # (avg, sec, geo_open, markers, first_sent, body_snippet)
for row in rows[1:]:
    if not row or len(row) <= max(lv_c, tx_c): continue
    lval = str(row[lv_c]).strip() if row[lv_c] else ""
    txt  = str(row[tx_c]).strip() if row[tx_c] else ""
    sec  = str(row[sc_c]).strip() if (sc_c and row[sc_c]) else ""
    if not lval or not txt: continue
    m = re.search(r"\d+", lval)
    if not m or m.group() != "3": continue
    if sec not in ("World Tour", "Focus", "People"): continue
    yr = None
    if dt_c is not None and len(row) > dt_c and row[dt_c]:
        ym = _YR.search(str(row[dt_c]))
        if ym: yr = int(ym.group())
    if yr is not None and yr < 2024: continue
    a   = avg_sl(txt)
    fsm = _FIRST_SENT_END.search(txt[:400])
    fs  = txt[:fsm.start()].strip() if fsm else txt[:250].strip()
    go  = bool(_GEO_OPENING.match(fs))
    mc  = len(_GEO_MARKERS.findall(txt))
    results.append((a, sec, go, mc, fs, txt))

# 1. World Tour 탈락 기사 (avg < AVG_MIN)
print("=" * 70)
print(f"World Tour 2024~ L3 탈락 기사 (avg < {AVG_MIN})")
print("=" * 70)
wt_fails = [(a,go,mc,fs,txt) for a,sec,go,mc,fs,txt in results if sec=="World Tour" and a < AVG_MIN]
for a,go,mc,fs,txt in sorted(wt_fails):
    print(f"\navg={a:.2f}  geo_open={go}  markers={mc}")
    print(f"  first_sent: {fs}")
    # 전체 텍스트에서 마커 단어 찾아 표시
    marker_hits = _GEO_MARKERS.findall(txt)
    print(f"  marker_hits: {marker_hits}")
    print(f"  body[150:350]: {txt[150:350].replace(chr(10),' ')}")

# 2. Focus / People 에서 geo_open=True 인 기사 (false positive 후보)
print()
print("=" * 70)
print("Focus/People geo_open=True (false positive 후보)")
print("=" * 70)
fp = [(a,sec,go,mc,fs,txt) for a,sec,go,mc,fs,txt in results
      if sec in ("Focus","People") and go]
if not fp:
    print("  없음")
else:
    for a,sec,go,mc,fs,txt in fp:
        print(f"\n[{sec}] avg={a:.2f} geo_open={go} markers={mc}")
        print(f"  first_sent: {fs}")
