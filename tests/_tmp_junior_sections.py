"""JUNIOR 섹션 전수 분석: World Tour 카운트·샘플 + 섹션별 성격 + L3 정화 분포."""
import sys, io, re, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl
from agents.sub_agents.cefr_checker import LEVELS
from agents.sub_agents.article_classifier import classify

ARTICLES  = r"C:\Users\jp\Desktop\기사\articles.xlsx"
_SE       = re.compile(r"(?<=[.!?])\s+")
_YEAR_RE  = re.compile(r"\b(20\d{2})\b")
YEAR_CUTOFF = 2024
AVG_MIN   = LEVELS["JUNIOR_L3"].avg_min  # 11.5

EXCL_BASE = {
    "Photo News","Briefs","Star Brief","News in Brief","Cartoon",
    "Did You Know","Did You Know?","Debating","Cover","Q & A","NE You",
    "My Journal","Book Review","Stories","Story",
    "Readings for Junior","VoA Broadcast News","Think About It","My Diary",
    "Pros & Cons",
}

def avg_sl(t):
    p = [len(re.findall(r"[A-Za-z']+", s)) for s in _SE.split(t.strip())]
    p = [w for w in p if w >= 1]
    return sum(p) / len(p) if p else 0.0

def pct(xs, p):
    s = sorted(xs)
    if not s: return 0.0
    idx = (len(s)-1)*p/100
    lo = int(idx); hi = min(lo+1, len(s)-1)
    return s[lo] + (s[hi]-s[lo])*(idx-lo)

wb   = openpyxl.load_workbook(ARTICLES, read_only=True, data_only=True)
ws   = wb["JUNIOR"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
lv_c = next(i for i,h in enumerate(hdr) if "레벨"  in h or "level"   in h.lower())
tx_c = next(i for i,h in enumerate(hdr) if "본문"  in h or "text"    in h.lower())
sc_c = next((i for i,h in enumerate(hdr) if "섹션"  in h or "section" in h.lower()), None)
dt_c = next((i for i,h in enumerate(hdr) if "날짜"  in h or "date"    in h.lower()), None)
ttl_c= next((i for i,h in enumerate(hdr) if "제목"  in h or "title"   in h.lower()), None)

# ── 수집: 전체 JUNIOR (연도 무관, 섹션 기본 EXCLUDE만) ──────────────────
# section → {L1:n, L2:n, L3:n, total:n, avgs:[], wt_samples:[(ttl,txt)]}
sec_stats = collections.defaultdict(lambda: {"L1":0,"L2":0,"L3":0,"total":0,"avgs":[],"samples":[]})
wt_all    = []   # (level, yr, avg, ttl, txt) — World Tour 전수

# 2024~ ARTICLE 풀 (EXCL_BASE 적용, classifier 적용)
pool_2024       = []   # (avg, sec, ttl, txt) — 모든 섹션
pool_no_wt_2024 = []   # World Tour 제외

for row in rows[1:]:
    if not row or len(row) <= max(lv_c, tx_c): continue
    lval = str(row[lv_c]).strip() if row[lv_c] else ""
    txt  = str(row[tx_c]).strip() if row[tx_c] else ""
    sec  = str(row[sc_c]).strip() if (sc_c and row[sc_c]) else ""
    ttl  = str(row[ttl_c]).strip() if (ttl_c and row[ttl_c]) else ""
    if not lval or len(txt) < 50: continue
    if len(re.findall(r"[A-Za-z']+", txt)) < 80: continue
    m = re.search(r"\d+", lval)
    if not m: continue
    lnum = m.group()
    key  = f"JUNIOR_L{lnum}"
    if key not in LEVELS: continue

    yr = None
    if dt_c is not None and len(row) > dt_c and row[dt_c]:
        ym = _YEAR_RE.search(str(row[dt_c]))
        if ym: yr = int(ym.group())

    a = avg_sl(txt)
    if a < 1.0: continue

    # World Tour 전수 (연도 무관)
    if sec == "World Tour":
        wt_all.append((f"L{lnum}", yr, a, ttl, txt))

    # 섹션별 통계 (연도 무관, 기본 EXCL만)
    if sec not in EXCL_BASE:
        st = sec_stats[sec]
        st["total"] += 1
        st[f"L{lnum}"] = st.get(f"L{lnum}", 0) + 1
        st["avgs"].append(a)
        if len(st["samples"]) < 3:
            st["samples"].append((ttl, txt[:120]))

    # 2024~ L3 분포 (기본 EXCL + classifier)
    if lnum != "3": continue
    if sec in EXCL_BASE: continue
    cls = classify(txt, key)
    if cls.skip_cefr: continue
    if yr is not None and yr < YEAR_CUTOFF: continue
    pool_2024.append((a, sec, ttl, txt))
    if sec != "World Tour":
        pool_no_wt_2024.append((a, sec, ttl, txt))

# ══════════════════════════════════════════════════════════════
# 1. World Tour 레벨·연도별 카운트
# ══════════════════════════════════════════════════════════════
print("=" * 65)
print("World Tour 레벨별 건수 (연도 전체)")
print("=" * 65)
wt_by_lv = collections.Counter(x[0] for x in wt_all)
print(f"  L1={wt_by_lv.get('L1',0)}  L2={wt_by_lv.get('L2',0)}  L3={wt_by_lv.get('L3',0)}  합계={len(wt_all)}")

# 연도별
wt_yr = collections.Counter(x[1] for x in wt_all if x[1])
print("\n  연도별 건수:")
for yr in sorted(wt_yr):
    print(f"    {yr}: {wt_yr[yr]}건")

# ══════════════════════════════════════════════════════════════
# 2. World Tour 샘플 6건 — 정형 국가소개 외 다른 형식 있는지
# ══════════════════════════════════════════════════════════════
print()
print("=" * 65)
print("World Tour 샘플 8건 (레벨·연도 고르게, 본문 앞 200자)")
print("=" * 65)
# L1 2건, L2 3건, L3 3건
import random
random.seed(42)
def pick(lv, n):
    sub = [x for x in wt_all if x[0] == lv and x[1] and x[1] >= 2024]
    if not sub:
        sub = [x for x in wt_all if x[0] == lv]
    return sub[:n] if len(sub) <= n else random.sample(sub, n)

for lv, n in [("L1",2),("L2",3),("L3",3)]:
    for lvl, yr, a, ttl, txt in pick(lv, n):
        preview = txt[:200].replace("\n"," ")
        print(f"\n[{lvl} {yr}] avg={a:.2f} | {ttl[:55]}")
        print(f"  {preview}")

# ══════════════════════════════════════════════════════════════
# 3. JUNIOR 섹션별 전수: 건수·레벨 분포·avg 중앙값
# ══════════════════════════════════════════════════════════════
print()
print("=" * 65)
print("JUNIOR 섹션별 전수 (기본 EXCL 이후, 건수 내림차순)")
print(f"{'섹션':<22} {'합계':>5}  {'L1':>4} {'L2':>4} {'L3':>4}  {'avg_p50':>7}")
print("-" * 65)
for sec, st in sorted(sec_stats.items(), key=lambda x: -x[1]["total"]):
    p50 = pct(st["avgs"], 50) if st["avgs"] else 0
    l1  = st.get("L1",0); l2 = st.get("L2",0); l3 = st.get("L3",0)
    print(f"{sec:<22} {st['total']:>5}  {l1:>4} {l2:>4} {l3:>4}  {p50:>7.1f}")

# ══════════════════════════════════════════════════════════════
# 4. People·Focus 샘플 각 2건 — 정형인지 확인
# ══════════════════════════════════════════════════════════════
print()
print("=" * 65)
print("People / Focus 샘플 각 3건 (본문 앞 150자)")
print("=" * 65)
for target_sec in ["People", "Focus"]:
    cands = [x for x in pool_2024 if x[1] == target_sec]
    picks = cands[:3]
    print(f"\n[{target_sec}]")
    for a, sec, ttl, txt in picks:
        preview = txt[:150].replace("\n"," ")
        print(f"  avg={a:.2f} | {ttl[:55]}")
        print(f"  {preview}")

# ══════════════════════════════════════════════════════════════
# 5. JUNIOR_L3 2024~ 분포 비교: 전체 vs World Tour 제외
# ══════════════════════════════════════════════════════════════
print()
print("=" * 65)
print("JUNIOR_L3 2024~ 분포 비교")
print("=" * 65)
for label, pool in [("전체(기존)", pool_2024), ("World Tour 제외", pool_no_wt_2024)]:
    avgs = [x[0] for x in pool]
    n    = len(avgs)
    fail = sum(1 for a in avgs if a < AVG_MIN)
    if not avgs:
        print(f"{label}: 데이터 없음"); continue
    print(f"\n{label}  n={n}  탈락={fail}건({fail/n*100:.1f}%)  avg_min={AVG_MIN}")
    print(f"  p5={pct(avgs,5):.2f}  p10={pct(avgs,10):.2f}  p25={pct(avgs,25):.2f}  p50={pct(avgs,50):.2f}  p75={pct(avgs,75):.2f}")
