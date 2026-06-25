"""JUNIOR M 분포 진단 — 섹션 구성 확인 + 필터 후 깨끗한 분포 + 하단 경계 샘플."""
import sys, io, re, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl
from agents.sub_agents.cefr_checker import validate
from agents.sub_agents.article_classifier import classify, ArticleType

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"

EXCLUDE_SECTIONS = {
    "Photo News", "Briefs", "Star Brief", "News in Brief",
    "Cartoon", "Did You Know", "Did You Know?", "Debating", "Cover", "Q & A",
    "NE You",
}
MIN_WC = 100

def pct(xs, p):
    s = sorted(xs)
    return s[min(int(len(s) * p / 100), len(s) - 1)]

# ── 데이터 로드 ────────────────────────────────────────────────────────────
wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws = wb["JUNIOR M"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]

lv_col  = next(i for i,h in enumerate(hdr) if "레벨" in h or "level"   in h.lower())
tx_col  = next(i for i,h in enumerate(hdr) if "본문" in h or "text"    in h.lower())
sc_col  = next(i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower())

# ── 1. 섹션별 구성 (레벨별) ────────────────────────────────────────────────
print("=" * 72)
print("1. JUNIOR M 섹션별 구성 — 레벨별 기사 수 + 평균 avg + classify 비율")
print("=" * 72)

# {lv: {sec: [avg_list, brief_n, dialogue_n, article_n]}}
sec_data: dict[str, dict[str, list]] = {}

for row in rows[1:]:
    if not row or len(row) <= max(lv_col, tx_col, sc_col): continue
    lv  = str(row[lv_col]).strip() if row[lv_col]  else ""
    txt = str(row[tx_col]).strip() if row[tx_col]  else ""
    sec = str(row[sc_col]).strip() if row[sc_col]  else ""
    if not lv or len(txt) < 30: continue
    m = re.search(r"\d+", lv)
    if not m: continue
    key = f"JUNIORM_L{m.group()}"
    if key not in ("JUNIORM_L1", "JUNIORM_L2"): continue

    wc = len(re.findall(r"[A-Za-z']+", txt))
    r  = classify(txt, key)
    avg = validate(txt, key).avg_sentence_len

    if key not in sec_data: sec_data[key] = {}
    if sec not in sec_data[key]:
        sec_data[key][sec] = []   # [avg, type_str]
    sec_data[key][sec].append((avg, r.article_type.value, wc))

for lv_key in ("JUNIORM_L1", "JUNIORM_L2"):
    if lv_key not in sec_data: continue
    print(f"\n  ▶ {lv_key}")
    print(f"  {'섹션':<22} {'n':>5}  {'avg_p50':>7}  {'ARTICLE':>8}  {'DIALOGUE':>9}  {'BRIEF':>6}  {'제외여부'}")
    print(f"  {'─'*22} {'─'*5}  {'─'*7}  {'─'*8}  {'─'*9}  {'─'*6}  {'─'*6}")
    for sec, items in sorted(sec_data[lv_key].items(), key=lambda x: -len(x[1])):
        avgs  = [a for a,_,_ in items]
        types = [t for _,t,_ in items]
        n_art = types.count("ARTICLE")
        n_dlg = types.count("DIALOGUE")
        n_brf = types.count("BRIEF")
        p50v  = pct(avgs, 50) if avgs else 0
        excl  = "⛔제외" if sec in EXCLUDE_SECTIONS else ""
        print(f"  {sec:<22} {len(items):>5}  {p50v:>7.1f}  {n_art:>8}  {n_dlg:>9}  {n_brf:>6}  {excl}")

# ── 2. 필터 후 깨끗한 분포 ─────────────────────────────────────────────────
print()
print("=" * 72)
print("2. 필터 후 깨끗한 분포 (EXCLUDE_SECTIONS + wc<100 + BRIEF/DIALOGUE 제외)")
print("=" * 72)

clean: dict[str, list[float]] = {"JUNIORM_L1": [], "JUNIORM_L2": []}
raw_for_sample: dict[str, list[tuple]] = {"JUNIORM_L1": [], "JUNIORM_L2": []}

for row in rows[1:]:
    if not row or len(row) <= max(lv_col, tx_col, sc_col): continue
    lv  = str(row[lv_col]).strip() if row[lv_col]  else ""
    txt = str(row[tx_col]).strip() if row[tx_col]  else ""
    sec = str(row[sc_col]).strip() if row[sc_col]  else ""
    if not lv or len(txt) < 30: continue
    m = re.search(r"\d+", lv)
    if not m: continue
    key = f"JUNIORM_L{m.group()}"
    if key not in clean: continue

    if sec in EXCLUDE_SECTIONS: continue
    wc = len(re.findall(r"[A-Za-z']+", txt))
    if wc < MIN_WC: continue
    r = classify(txt, key)
    if r.skip_cefr: continue

    avg = validate(txt, key).avg_sentence_len
    clean[key].append(avg)
    raw_for_sample[key].append((avg, sec, txt))

print(f"\n  {'레벨':<14} {'n':>5}  {'p10':>6} {'p25':>6} {'p50':>6} {'p75':>6}")
print(f"  {'─'*14} {'─'*5}  {'─'*6} {'─'*6} {'─'*6} {'─'*6}")

# JUNIOR 레벨 참고값
JUNIOR_REF = {
    "JUNIOR_L1": (267, 10.9, 11.6, 12.8, 14.0),
    "JUNIOR_L2": (403, 10.8, 11.7, 12.7, 13.9),
    "JUNIOR_L3": (134, 11.5, 12.3, 13.6, 15.4),
}
for ref_key, (n, p10v, p25v, p50v, p75v) in JUNIOR_REF.items():
    print(f"  {ref_key:<14} {n:>5}  {p10v:>6.1f} {p25v:>6.1f} {p50v:>6.1f} {p75v:>6.1f}  (참고: JUNIOR)")

print()
for lv_key in ("JUNIORM_L1", "JUNIORM_L2"):
    xs = clean[lv_key]
    if not xs:
        print(f"  {lv_key:<14} 데이터 없음")
        continue
    p10v = pct(xs, 10); p25v = pct(xs, 25)
    p50v = pct(xs, 50); p75v = pct(xs, 75)
    cmp  = "▲ JUNIOR_L3 p50 초과" if p50v > 13.6 else \
           "▲ JUNIOR_L1 p50 초과" if p50v > 12.8 else \
           "= JUNIOR_L1 수준"     if p50v > 11.8 else \
           "▼ JUNIOR_L1 이하"
    print(f"  {lv_key:<14} {len(xs):>5}  {p10v:>6.1f} {p25v:>6.1f} {p50v:>6.1f} {p75v:>6.1f}  {cmp}")

# ── 3. 하단 경계 기사 10개씩 샘플 ─────────────────────────────────────────
print()
print("=" * 72)
print("3. 하단 경계 기사 10개 — 최저 avg 순 (섹션 + avg + 본문 앞 120자)")
print("=" * 72)

for lv_key in ("JUNIORM_L1", "JUNIORM_L2"):
    items = raw_for_sample[lv_key]
    if not items: continue
    items_sorted = sorted(items, key=lambda x: x[0])
    print(f"\n  ▶ {lv_key} 최저 10건")
    print(f"  {'#':>3}  {'avg':>5}  {'섹션':<20}  본문 앞 120자")
    print(f"  {'─'*3}  {'─'*5}  {'─'*20}  {'─'*50}")
    for i, (avg, sec, txt) in enumerate(items_sorted[:10], 1):
        preview = txt[:120].replace("\n", " ")
        print(f"  {i:>3}  {avg:>5.1f}  {sec:<20}  {preview}")
