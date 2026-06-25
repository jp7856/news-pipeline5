"""TIMES_L1/L2/L3 FK 분포 — 진짜 뉴스 기사 기준 (Pros & Cons 추가 제외).

섹션 정리:
  기존 EXCLUDE_SECTIONS
  + "Pros & Cons"  (토론형 의견 포맷 — 뉴스 산문 아님, ARTICLE로 분류되지만 제외)

대상: avg_min 통과 기사 (CEFR 게이트가 실제로 적용되는 풀).
"""
import sys, io, re, bisect
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
    "Pros & Cons",    # 추가 — 토론형 의견 포맷
}

AVG_MINS = {"TIMES_L1": 10.5, "TIMES_L2": 13.5, "TIMES_L3": 15.5}

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
lv_col = next(i for i,h in enumerate(hdr) if "레벨" in h or "level"   in h.lower())
tx_col = next(i for i,h in enumerate(hdr) if "본문" in h or "text"    in h.lower())
sc_col = next(i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower())

fk_data: dict[str, list[float]] = {"TIMES_L1": [], "TIMES_L2": [], "TIMES_L3": []}

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
    if not m: continue
    key = f"TIMES_L{m.group()}"
    if key not in fk_data: continue
    if classify(txt, key).skip_cefr: continue
    avg = validate(txt, key).avg_sentence_len
    if avg < AVG_MINS[key]: continue
    fk_data[key].append(textstat.flesch_kincaid_grade(txt))

def pct(d_sorted: list, p: float) -> float:
    """p번째 백분위수 (0≤p≤100)."""
    if not d_sorted: return 0.0
    idx = (len(d_sorted) - 1) * p / 100
    lo, hi = int(idx), min(int(idx) + 1, len(d_sorted) - 1)
    return d_sorted[lo] + (d_sorted[hi] - d_sorted[lo]) * (idx - lo)

print("섹션 정리: 기존 EXCLUDE_SECTIONS + Pros & Cons\n")

# ── 1. 세 레벨 FK 분포 ────────────────────────────────────────────────────────
print("=" * 72)
print("1. TIMES_L1/L2/L3 FK 분포  (avg_min 통과 뉴스 기사 기준)")
print("=" * 72)
HDR = f"{'레벨':<12} {'n':>5}  {'p5':>5} {'p10':>5} {'p15':>5} {'p25':>5} {'p50':>5} {'p75':>5} {'p90':>5}"
print(HDR)
print("-" * 72)

ps_store: dict[str, dict[float, float]] = {}
for lv in ["TIMES_L1", "TIMES_L2", "TIMES_L3"]:
    d = sorted(fk_data[lv])
    n = len(d)
    ps = {p: pct(d, p) for p in [5, 10, 15, 25, 50, 75, 90]}
    ps_store[lv] = ps
    row_str = (f"{lv:<12} {n:>5}  "
               f"{ps[5]:>5.1f} {ps[10]:>5.1f} {ps[15]:>5.1f} "
               f"{ps[25]:>5.1f} {ps[50]:>5.1f} {ps[75]:>5.1f} {ps[90]:>5.1f}")
    print(row_str)

# ── 2. TIMES_L2 기준점 — 경계 샘플 [3][4][5] 위치 ────────────────────────────
print()
print("=" * 72)
print("2. TIMES_L2 경계 샘플 [3][4][5] 위치")
print("   (analyze_times_l2_fk_floor.py 출력 기준)")
print("=" * 72)
d2 = sorted(fk_data["TIMES_L2"])
n2 = len(d2)

REF = [
    (6.83, "[3] Global     — 12 fingers 인간흥미, 직접 말걸기"),
    (6.93, "[4] Lifestyle  — food fights listicle"),
    (7.04, "[5] Lifestyle  — screen time feature"),
]
print(f"{'FK':>6}  {'분위':>8}  설명")
print("-" * 60)
for fk_val, label in REF:
    rank = bisect.bisect_right(d2, fk_val)
    tile = rank / n2 * 100
    print(f"  {fk_val:.2f}  하위{tile:>5.1f}%  {label}")

# ── 3. TIMES_L2: fk_min 후보별 탈락 건수 ─────────────────────────────────────
print()
print("=" * 72)
print("3. TIMES_L2 fk_min 후보별 탈락 건수")
print("   (fk_min 미만이면 탈락 — 즉 FK < fk_min)")
print("=" * 72)
ps2 = ps_store["TIMES_L2"]
print(f"  {'후보':<8} {'fk_min':>6}  {'탈락건':>6}  {'탈락%':>6}")
print(f"  {'-'*40}")
for label, val in [("p10", ps2[10]), ("p15", ps2[15])]:
    rejected = bisect.bisect_left(d2, val)   # FK < val 건수
    print(f"  {label:<8} {val:>6.2f}  {rejected:>6}건  {rejected/n2*100:>5.1f}%")

# 참고: 이전 분석(Pros&Cons 포함) 대비 n 변화
print()
prev_n = {"TIMES_L1": 4272, "TIMES_L2": 5859, "TIMES_L3": 3878}
print("참고: Pros & Cons 제외에 따른 n 변화")
for lv in ["TIMES_L1", "TIMES_L2", "TIMES_L3"]:
    d = sorted(fk_data[lv])
    diff = len(d) - prev_n[lv]
    print(f"  {lv}: {prev_n[lv]}건 → {len(d)}건  (차이 {diff:+d}건)")
