"""검증: (1) geo_template false positive 확인 (2) Debate 제외 효과 (3) JUNIOR 전 레벨 탈락률."""
import sys, io, re, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl
from agents.sub_agents.cefr_checker import LEVELS
from agents.sub_agents.article_classifier import classify, ArticleType

ARTICLES  = r"C:\Users\jp\Desktop\기사\articles.xlsx"
_SE       = re.compile(r"(?<=[.!?])\s+")
_YEAR_RE  = re.compile(r"\b(20\d{2})\b")
YEAR_CUTOFF = 2024

EXCL = {
    "Photo News","Briefs","Star Brief","News in Brief","Cartoon",
    "Did You Know","Did You Know?","Debating","Cover","Q & A","NE You",
    "My Journal","Book Review","Stories","Story",
    "Readings for Junior","VoA Broadcast News","Think About It","My Diary",
    "Pros & Cons",
    "Debate",   # 추가
}

def avg_sl(t):
    p = [len(re.findall(r"[A-Za-z']+", s)) for s in _SE.split(t.strip())]
    p = [w for w in p if w >= 1]
    return sum(p) / len(p) if p else 0.0

wb   = openpyxl.load_workbook(ARTICLES, read_only=True, data_only=True)
ws   = wb["JUNIOR"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
lv_c = next(i for i,h in enumerate(hdr) if "레벨"  in h or "level"   in h.lower())
tx_c = next(i for i,h in enumerate(hdr) if "본문"  in h or "text"    in h.lower())
sc_c = next((i for i,h in enumerate(hdr) if "섹션"  in h or "section" in h.lower()), None)
dt_c = next((i for i,h in enumerate(hdr) if "날짜"  in h or "date"    in h.lower()), None)

# ── 수집: JUNIOR 전 레벨 (2024~, EXCL 적용) ──────────────────────────────
# key → {n, fail, geo_skip, dialogue_skip, brief_skip, debate_excl}
stats = {}
# geo_template false positive 후보: World Tour 외 섹션에서 geo_template 감지된 것
geo_fp_candidates = []
# World Tour 섹션 geo 감지 현황
geo_wt_hit   = []  # 잡힌 것
geo_wt_miss  = []  # 안 잡힌 것

for row in rows[1:]:
    if not row or len(row) <= max(lv_c, tx_c): continue
    lval = str(row[lv_c]).strip() if row[lv_c] else ""
    txt  = str(row[tx_c]).strip() if row[tx_c] else ""
    sec  = str(row[sc_c]).strip() if (sc_c and row[sc_c]) else ""
    if not lval or len(txt) < 50: continue
    if len(re.findall(r"[A-Za-z']+", txt)) < 80: continue
    m = re.search(r"\d+", lval)
    if not m or int(m.group()) == 0: continue
    key = f"JUNIOR_L{m.group()}"
    if key not in LEVELS: continue
    yr = None
    if dt_c is not None and len(row) > dt_c and row[dt_c]:
        ym = _YEAR_RE.search(str(row[dt_c]))
        if ym: yr = int(ym.group())
    if yr is not None and yr < YEAR_CUTOFF: continue

    # Debate 제외 처리
    if sec == "Debate":
        b = stats.setdefault(key, {"n":0,"fail":0,"geo":0,"dlg":0,"brief":0,"debate":0})
        b["debate"] += 1
        continue

    # 기타 EXCL 섹션
    if sec in EXCL: continue

    cls = classify(txt, key)
    b   = stats.setdefault(key, {"n":0,"fail":0,"geo":0,"dlg":0,"brief":0,"debate":0})

    if cls.skip_cefr:
        if cls.geo_template:
            b["geo"] += 1
            # World Tour 섹션이 아닌 곳에서 geo_template 잡히면 false positive 후보
            if sec != "World Tour":
                geo_fp_candidates.append((key, sec, txt[:200]))
        elif cls.article_type == ArticleType.DIALOGUE:
            b["dlg"] += 1
        else:
            b["brief"] += 1
        continue

    a = avg_sl(txt)
    if a < 1.0: continue
    b["n"] += 1
    if a < LEVELS[key].avg_min:
        b["fail"] += 1

    # World Tour 섹션 geo 감지 여부 추적
    if sec == "World Tour":
        if cls.geo_template:
            geo_wt_hit.append((a, txt[:120]))
        else:
            geo_wt_miss.append((a, txt[:120]))

# ══════════════════════════════════════════════════════════════
# 1. geo_template false positive 확인
# ══════════════════════════════════════════════════════════════
print("=" * 65)
print("1. geo_template 감지: World Tour 섹션 결과")
print("=" * 65)
print(f"  잡힘(geo_template=True): {len(geo_wt_hit)}건")
for a, preview in geo_wt_hit[:5]:
    print(f"    avg={a:.2f} | {preview}")
print(f"\n  안 잡힘(ARTICLE로 통과): {len(geo_wt_miss)}건")
for a, preview in geo_wt_miss[:5]:
    print(f"    avg={a:.2f} | {preview}")

print()
print("=" * 65)
print("2. false positive 후보 (World Tour 외 섹션에서 geo_template 감지)")
print("=" * 65)
if not geo_fp_candidates:
    print("  없음 — false positive 0건")
else:
    for key, sec, preview in geo_fp_candidates:
        print(f"  [{key}] sec={sec} | {preview}")

# ══════════════════════════════════════════════════════════════
# 3. JUNIOR 전 레벨 탈락률
# ══════════════════════════════════════════════════════════════
print()
print("=" * 65)
print("3. JUNIOR L1/L2/L3 탈락률 (2024~, Debate 제외 + geo_template 면제)")
print(f"{'레벨':<12} {'avg_min':>7} {'ARTICLE n':>10} {'탈락':>6} {'탈락률':>6}"
      f"  │ {'Debate제외':>10} {'geo면제':>7} {'DIALOGUE':>9} {'단신':>5}")
print("─" * 80)
for key in ["JUNIOR_L1","JUNIOR_L2","JUNIOR_L3"]:
    b = stats.get(key, {})
    n    = b.get("n", 0)
    fail = b.get("fail", 0)
    geo  = b.get("geo", 0)
    dlg  = b.get("dlg", 0)
    bf   = b.get("brief", 0)
    dbt  = b.get("debate", 0)
    rate = fail/n*100 if n else 0
    spec = LEVELS[key]
    print(f"{key:<12} {spec.avg_min:>7}  {n:>9}  {fail:>5}  {rate:>5.1f}%"
          f"  │ {dbt:>9}  {geo:>6}  {dlg:>8}  {bf:>4}")
