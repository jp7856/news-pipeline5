"""TIMES_L1 avg_sentence_len 분포 — 분류기 전후 비교 + avg_min 후보별 거부율."""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import openpyxl
from agents.sub_agents.cefr_checker import validate
from agents.sub_agents.article_classifier import classify, ArticleType

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"
EXCLUDE_SECTIONS = {
    "Photo News", "Briefs", "Star Brief", "News in Brief",
    "Cartoon", "Did You Know", "Did You Know?", "Debating", "Cover", "Q & A",
}
MIN_WC = 100

wb   = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws   = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
lv_col  = next(i for i,h in enumerate(hdr) if "레벨" in h or "level" in h.lower())
tx_col  = next(i for i,h in enumerate(hdr) if "본문" in h or "text" in h.lower())
sc_col  = next(i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower())

avgs_all   = []   # 섹션·단신 필터만 (분류기 미적용)
avgs_clean = []   # ARTICLE만
dlg_avgs   = []   # DIALOGUE만

for row in rows[1:]:
    if not row or len(row) <= max(lv_col, tx_col): continue
    lv  = str(row[lv_col]).strip() if row[lv_col] else ""
    txt = str(row[tx_col]).strip() if row[tx_col] else ""
    sec = str(row[sc_col]).strip() if row[sc_col] else ""
    if lv != "LEVEL 1" or len(txt) < 50: continue
    if sec in EXCLUDE_SECTIONS: continue
    wc = len(re.findall(r"[A-Za-z']+", txt))
    if wc < MIN_WC: continue

    avg = validate(txt, "TIMES_L1").avg_sentence_len
    avgs_all.append(avg)
    cls = classify(txt, "TIMES_L1")
    if cls.article_type == ArticleType.ARTICLE:
        avgs_clean.append(avg)
    elif cls.article_type == ArticleType.DIALOGUE:
        dlg_avgs.append(avg)


def pct(xs, p):
    s = sorted(xs)
    return s[min(int(len(s) * p / 100), len(s) - 1)]


def below(xs, threshold):
    return sum(1 for x in xs if x < threshold)


print("=" * 60)
print("TIMES_L1 avg_sentence_len 분포 (분류기 전후 비교)")
print("=" * 60)
print(f"{'':8} {'분류기 전':>12} {'분류기 후(ARTICLE)':>18} {'변화':>8}")
print(f"{'':8} {'n='+str(len(avgs_all)):>12} {'n='+str(len(avgs_clean)):>18}")
print("─" * 52)
for p in [5, 10, 15, 20, 25, 50, 75, 90]:
    before = pct(avgs_all, p)
    after  = pct(avgs_clean, p)
    diff   = after - before
    sign   = "+" if diff >= 0 else ""
    print(f"  p{p:<4}     {before:>12.2f} {after:>18.2f}  {sign}{diff:.2f}")

print()
print("=" * 60)
print("avg_min 후보별 거부율 (분류기 후 ARTICLE 기준)")
print("=" * 60)
print(f"  {'후보':>5}  {'거부건수':>8}  {'거부율':>7}  비고")
print("─" * 45)
for c in [9.0, 9.5, 10.0, 10.5, 11.0]:
    n    = below(avgs_clean, c)
    rate = n / len(avgs_clean) * 100
    mark = "  ← 현행" if c == 10.5 else ""
    print(f"  {c:>5.1f}  {n:>8}건  {rate:>6.1f}%{mark}")

print()
print("=" * 60)
print(f"제외된 DIALOGUE {len(dlg_avgs)}건의 avg 분포")
print("=" * 60)
if dlg_avgs:
    dlg_avgs.sort()
    print(f"  min={dlg_avgs[0]:.1f}, p25={pct(dlg_avgs,25):.1f}, "
          f"p50={pct(dlg_avgs,50):.1f}, p75={pct(dlg_avgs,75):.1f}, "
          f"max={dlg_avgs[-1]:.1f}")
    print(f"  10.5 미만: {below(dlg_avgs,10.5)}건 "
          f"({below(dlg_avgs,10.5)/len(dlg_avgs)*100:.0f}%)")
    print(f"  → DIALOGUE가 낮은 avg에 몰려있으면 제거 시 p10 상승 폭 큼")
