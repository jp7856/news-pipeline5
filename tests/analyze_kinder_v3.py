"""KINDER 분포 v3 + KIDS_L3 샘플.

KINDER EXCLUDE 변경:
  + Think About It  (토론/의견나열 포맷 — 전부 제외)
  + My Diary        (1인칭 일기체 — 전부 제외)
  Speak Out         섹션 제외 안 함, classifier 판정으로만 필터
"""
import sys, io, re, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl
from agents.sub_agents.article_classifier import classify

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"
random.seed(42)

EXCLUDE_SECTIONS_KINDER = {
    "Photo News",
    "NE You",
    "Cover",
    "Did You Know", "Did You Know?",
    "Cartoon",
    "Q & A",
    "Think About It",   # 토론/의견나열 포맷
    "My Diary",         # 1인칭 일기체
    # Speak Out → 섹션 제외 안 함, classifier 판정 사용
}

EXCLUDE_SECTIONS_KIDS = {
    "Photo News", "NE You", "Cover",
    "Did You Know", "Did You Know?", "Debating", "Q & A", "Cartoon",
}

_SENT_END = re.compile(r'(?<=[.!?])\s+')

def avg_sent_len(text: str) -> float:
    parts = _SENT_END.split(text.strip())
    wcs   = [len(re.findall(r"[A-Za-z']+", p)) for p in parts]
    wcs   = [w for w in wcs if w >= 1]
    return sum(wcs) / len(wcs) if wcs else 0.0

def pct(d: list, p: float) -> float:
    if not d: return 0.0
    idx = (len(d) - 1) * p / 100
    lo  = int(idx); hi = min(lo + 1, len(d) - 1)
    return d[lo] + (d[hi] - d[lo]) * (idx - lo)

def load_ws(sheet_name: str):
    wb  = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
    ws  = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    hdr  = [str(c).strip() if c else "" for c in rows[0]]
    lv   = next(i for i,h in enumerate(hdr) if "레벨"  in h or "level"   in h.lower())
    tx   = next(i for i,h in enumerate(hdr) if "본문"  in h or "text"    in h.lower())
    sc   = next((i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower()), None)
    ttl  = next((i for i,h in enumerate(hdr) if "제목" in h or "title"   in h.lower()), None)
    return rows[1:], lv, tx, sc, ttl

def show_band_samples(items, p5v, p15v, n_pick=5):
    band = [(a, ttl, fmt, t) for a, ttl, fmt, t in items if p5v <= a <= p15v]
    if not band:
        band = [(a, ttl, fmt, t) for a, ttl, fmt, t in items if a <= p15v]
    band.sort(key=lambda x: x[0])
    step  = max(1, len(band) // n_pick)
    picks = [band[i] for i in range(0, min(len(band), step * n_pick), step)][:n_pick]
    print(f"  하위 분위(p5~p15) {len(band)}건 중 {len(picks)}개:")
    for i, (avg, ttl, fmt, txt) in enumerate(picks, 1):
        preview = txt[:200].replace("\n", " ")
        print(f"\n  [{i}] avg={avg:.1f}  포맷={fmt}  제목={ttl[:60] or '(없음)'}")
        print(f"       {preview}{'...' if len(txt)>200 else ''}")

# ══════════════════════════════════════════════════════════════════════════
# 1. KINDER — Speak Out classifier 분류 카운트
# ══════════════════════════════════════════════════════════════════════════
print("=" * 70)
print("Speak Out classifier 분류 카운트")
print("=" * 70)

rows_k, lv_k, tx_k, sc_k, ttl_k = load_ws("KINDER")
speak_article = 0; speak_dialogue = 0; speak_brief = 0
for row in rows_k:
    if not row: continue
    txt = str(row[tx_k]).strip() if row[tx_k] else ""
    sec = str(row[sc_k]).strip() if (sc_k and row[sc_k]) else ""
    lv  = str(row[lv_k]).strip() if row[lv_k] else ""
    if sec != "Speak Out" or not txt: continue
    m = re.search(r"\d+", lv)
    if not m: continue
    key = f"KINDER_L{m.group()}"
    wc = len(re.findall(r"[A-Za-z']+", txt))
    if wc < 5: continue
    cls = classify(txt, key)
    if   cls.article_type.value == "ARTICLE":  speak_article  += 1
    elif cls.article_type.value == "DIALOGUE": speak_dialogue += 1
    else:                                       speak_brief    += 1

total_speak = speak_article + speak_dialogue + speak_brief
print(f"  Speak Out 전체 {total_speak}건")
print(f"  ARTICLE  → 분석 유지 : {speak_article}건")
print(f"  DIALOGUE → 제외      : {speak_dialogue}건")
if speak_brief:
    print(f"  BRIEF    → 제외      : {speak_brief}건")

# ══════════════════════════════════════════════════════════════════════════
# 2. KINDER L1/L2 분포
# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("KINDER L1 / L2 분포 (Think About It + My Diary 제외 후)")
print("=" * 70)

kinder_data: dict[str, list] = {}
ex_sec = ex_cls = ex_empty = 0

for row in rows_k:
    if not row: continue
    lv  = str(row[lv_k]).strip()  if row[lv_k]  else ""
    txt = str(row[tx_k]).strip()  if row[tx_k]  else ""
    sec = str(row[sc_k]).strip()  if (sc_k  and row[sc_k])  else ""
    ttl = str(row[ttl_k]).strip() if (ttl_k and row[ttl_k]) else ""
    if not lv or not txt: continue
    m = re.search(r"\d+", lv)
    if not m: continue
    key = f"KINDER_L{m.group()}"
    wc = len(re.findall(r"[A-Za-z']+", txt))
    if wc < 5: ex_empty += 1; continue
    if sec in EXCLUDE_SECTIONS_KINDER: ex_sec += 1; continue
    cls = classify(txt, key)
    if cls.skip_cefr: ex_cls += 1; continue
    avg = avg_sent_len(txt)
    if avg < 1.0: ex_empty += 1; continue
    kinder_data.setdefault(key, []).append((avg, ttl, cls.article_type.value, txt))

total_art = sum(len(v) for v in kinder_data.values())
print(f"(섹션제외 {ex_sec}건 + classifier제외 {ex_cls}건 + 빈텍스트 {ex_empty}건,"
      f"  최종 ARTICLE {total_art}건)\n")

for key in ["KINDER_L1", "KINDER_L2"]:
    items = kinder_data.get(key, [])
    avgs  = sorted(x[0] for x in items)
    n = len(avgs)
    if n == 0: print(f"{key}: 데이터 없음"); continue
    p5v  = pct(avgs, 5);  p10v = pct(avgs, 10); p15v = pct(avgs, 15)
    p25v = pct(avgs, 25); p50v = pct(avgs, 50)
    print(f"── {key}  n={n} ──")
    print(f"  p5={p5v:.1f}  p10={p10v:.1f}  p15={p15v:.1f}  p25={p25v:.1f}  p50={p50v:.1f}")
    show_band_samples(items, p5v, p15v)
    print()

# ══════════════════════════════════════════════════════════════════════════
# 3. KIDS_L3 p5~p15 샘플
# ══════════════════════════════════════════════════════════════════════════
print("=" * 70)
print("KIDS_L3  p5~p15 구간 샘플")
print("=" * 70)

rows_kids, lv_kids, tx_kids, sc_kids, ttl_kids = load_ws("KIDS")
kids_l3: list = []

for row in rows_kids:
    if not row: continue
    lv  = str(row[lv_kids]).strip()  if row[lv_kids]  else ""
    txt = str(row[tx_kids]).strip()  if row[tx_kids]  else ""
    sec = str(row[sc_kids]).strip()  if (sc_kids  and row[sc_kids])  else ""
    ttl = str(row[ttl_kids]).strip() if (ttl_kids and row[ttl_kids]) else ""
    if not lv or not txt: continue
    m = re.search(r"\d+", lv)
    if not m or int(m.group()) != 3: continue
    if len(re.findall(r"[A-Za-z']+", txt)) < 5: continue
    if sec in EXCLUDE_SECTIONS_KIDS: continue
    cls = classify(txt, "KIDS_L3")
    if cls.skip_cefr: continue
    avg = avg_sent_len(txt)
    if avg < 1.0: continue
    kids_l3.append((avg, ttl, cls.article_type.value, txt))

avgs3 = sorted(x[0] for x in kids_l3)
n3    = len(avgs3)
p5v3  = pct(avgs3, 5); p15v3 = pct(avgs3, 15)
print(f"(n={n3}, p5={p5v3:.1f}~p15={p15v3:.1f})\n")
show_band_samples(kids_l3, p5v3, p15v3)
