"""TIMES L1/L2/L3 avg_min 경계 구간 샘플.

TIMES_L1: avg 8.5~10.5 구간 12개 (avg 오름차순)
TIMES_L2: 탈락 기사 8개 (낮은 끝 4 + 문턱 근처 4)
TIMES_L3: 탈락 기사 8개 (낮은 끝 4 + 문턱 근처 4)
PC(Pros&Cons) 제외. 값 변경 없음.
"""
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
    "My Journal","Book Review","Stories","Story",
    "Readings for Junior","VoA Broadcast News",
    "Think About It","My Diary",
    "Pros & Cons",   # 토론 활동지 — 이번 분석에서 제외
}

_SE = re.compile(r"(?<=[.!?])\s+")

def avg_sl(t: str) -> float:
    p = [len(re.findall(r"[A-Za-z']+", s)) for s in _SE.split(t.strip())]
    p = [w for w in p if w >= 1]
    return sum(p) / len(p) if p else 0.0

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws   = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
lv_c  = next(i for i,h in enumerate(hdr) if "레벨"  in h or "level"   in h.lower())
tx_c  = next(i for i,h in enumerate(hdr) if "본문"  in h or "text"    in h.lower())
sc_c  = next((i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower()), None)

# key → [(avg, fmt, sec, txt)]
pools: dict[str, list] = {"TIMES_L1": [], "TIMES_L2": [], "TIMES_L3": []}

for row in rows[1:]:
    if not row or len(row) <= max(lv_c, tx_c): continue
    lval = str(row[lv_c]).strip() if row[lv_c] else ""
    txt  = str(row[tx_c]).strip() if row[tx_c] else ""
    sec  = str(row[sc_c]).strip() if (sc_c and row[sc_c]) else ""
    if not lval or len(txt) < 50 or sec in EXCLUDE_SECTIONS: continue
    if len(re.findall(r"[A-Za-z']+", txt)) < 100: continue
    m = re.search(r"\d+", lval)
    if not m or m.group() not in ("1","2","3"): continue
    key = f"TIMES_L{m.group()}"
    if key not in LEVELS: continue
    cls = classify(txt, key)
    if cls.skip_cefr: continue
    a = avg_sl(txt)
    if a < 1.0: continue
    pools[key].append((a, cls.article_type.value, sec, txt))

def show(label, picks):
    print(f"\n{'='*72}")
    print(label)
    print(f"{'='*72}")
    for a, fmt, sec, txt in picks:
        preview = txt[:150].replace("\n", " ")
        print(f"[{a:.3f}] | {fmt} | {sec} | {preview}")

# ── TIMES_L1: avg 8.5~10.5 구간 12개 오름차순 ───────────────────────────
band_l1 = sorted(
    [(a,f,s,t) for a,f,s,t in pools["TIMES_L1"] if 8.5 <= a < 10.5],
    key=lambda x: x[0]
)
# 12개 균등 추출
def pick_spread(items, n):
    if len(items) <= n: return items
    step = (len(items)-1)/(n-1)
    return [items[round(step*i)] for i in range(n)]

picks_l1 = pick_spread(band_l1, 12)
show(
    f"TIMES_L1 | avg_min=10.5 | 구간 8.5~10.5 ({len(band_l1)}건 중 12개, avg 오름차순)",
    picks_l1,
)

# ── TIMES_L2: 탈락 기사 8개 (낮은 4 + 문턱 근처 4) ─────────────────────
fails_l2 = sorted(
    [(a,f,s,t) for a,f,s,t in pools["TIMES_L2"] if a < 13.5],
    key=lambda x: x[0]
)
picks_l2 = fails_l2[:4] + fails_l2[-4:]
show(
    f"TIMES_L2 | avg_min=13.5 | 탈락 {len(fails_l2)}건 중 8개 (낮은끝 4 + 문턱근처 4)",
    picks_l2,
)

# ── TIMES_L3: 탈락 기사 8개 (낮은 4 + 문턱 근처 4) ─────────────────────
fails_l3 = sorted(
    [(a,f,s,t) for a,f,s,t in pools["TIMES_L3"] if a < 15.5],
    key=lambda x: x[0]
)
picks_l3 = fails_l3[:4] + fails_l3[-4:]
show(
    f"TIMES_L3 | avg_min=15.5 | 탈락 {len(fails_l3)}건 중 8개 (낮은끝 4 + 문턱근처 4)",
    picks_l3,
)
