"""TIMES FK 하한 분석 — avg_min 통과 + FK 낮은 기사 규모 + fk_min 필요성 판단."""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import textstat
import openpyxl
from agents.sub_agents.cefr_checker import validate, LEVELS
from agents.sub_agents.article_classifier import classify

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"
EXCLUDE_SECTIONS = {
    "Photo News", "Briefs", "Star Brief", "News in Brief",
    "Cartoon", "Did You Know", "Did You Know?", "Debating", "Cover", "Q & A",
    "NE You",
    "My Journal", "Book Review",       # TIMES 독자 기고·서평
    "Stories", "Story",                # TIMES 창작소설
    "Readings for Junior",             # TIMES 보충읽기
    "VoA Broadcast News",              # TIMES L3 방송 스크립트
}
MIN_WC = 100

def pct(xs, p):
    s = sorted(xs)
    return s[min(int(len(s) * p / 100), len(s) - 1)]

# ── 0. CCTV 스타일 텍스트 — 게이트 통과 여부 ───────────────────────────────
# 이전 세션에서 "common, safer, money 수준 어휘인데 TIMES_L2였던 기사" 재현.
# avg_sentence_len을 TIMES_L2 기준(13.5) 이상으로 맞추고 어휘만 쉽게 구성.
CCTV_EASY = """\
Many cities around the world are now using CCTV cameras in public areas.
People say that CCTV cameras make streets safer because criminals are less likely to commit crimes when they know they are being watched.
Some studies have found that the number of crimes in areas with cameras is lower than in areas without them.
However, other people think that CCTV cameras are a problem because they watch everything people do in public.
They say that people should have the right to walk around the city without being recorded on camera.
It costs a lot of money to put up cameras and keep them working all the time.
Some people also say that cameras do not really stop crime, but just move it to other places where there are no cameras.
Cities need to think about whether the money spent on cameras is really making people safer or not.
"""

print("=" * 72)
print("0. CCTV 스타일 텍스트 — TIMES_L2 게이트 시뮬레이션")
print("   (avg_min 13.5 + fk_max 13.0 / fk_min 없음)")
print("=" * 72)
r_cctv = validate(CCTV_EASY, "TIMES_L2")
fk_cctv = textstat.flesch_kincaid_grade(CCTV_EASY)
wc_cctv = len(re.findall(r"[A-Za-z']+", CCTV_EASY))
print(f"\n  단어수   : {wc_cctv}")
print(f"  avg     : {r_cctv.avg_sentence_len:.1f}  (TIMES_L2 avg_min=13.5)")
print(f"  FK      : {fk_cctv:.1f}  (TIMES_L2 fk_max=13.0, fk_min=없음)")
print(f"  통과여부 : {'✓ 통과' if r_cctv.passed else '✗ 탈락'}  ({', '.join(r_cctv.violations) if r_cctv.violations else '위반 없음'})")
print(f"\n  → avg({r_cctv.avg_sentence_len:.1f}) ≥ 13.5 이고 FK({fk_cctv:.1f}) ≤ 13.0 이면 현재 게이트는 통과.")
print(f"    fk_min이 있었다면: FK {fk_cctv:.1f}가 기준 이하이면 탈락 가능.")

# ── 1. TIMES FK 분포 (필터 후 ARTICLE 전체) ───────────────────────────────
print()
print("=" * 72)
print("1. TIMES_L1/L2/L3 FK 분포 — 필터 후 ARTICLE 전체")
print("=" * 72)

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
lv_col = next(i for i,h in enumerate(hdr) if "레벨" in h or "level"   in h.lower())
tx_col = next(i for i,h in enumerate(hdr) if "본문" in h or "text"    in h.lower())
sc_col = next(i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower())

# (avg, fk) by level
data: dict[str, list[tuple]] = {"TIMES_L1": [], "TIMES_L2": [], "TIMES_L3": []}

for row in rows[1:]:
    if not row or len(row) <= max(lv_col, tx_col, sc_col): continue
    lv  = str(row[lv_col]).strip() if row[lv_col] else ""
    txt = str(row[tx_col]).strip() if row[tx_col] else ""
    sec = str(row[sc_col]).strip() if row[sc_col] else ""
    if not lv or len(txt) < 50: continue
    if sec in EXCLUDE_SECTIONS: continue
    wc = len(re.findall(r"[A-Za-z']+", txt))
    if wc < MIN_WC: continue
    m = re.search(r"\d+", lv)
    if not m: continue
    key = f"TIMES_L{m.group()}"
    if key not in data: continue
    if classify(txt, key).skip_cefr: continue

    avg = validate(txt, key).avg_sentence_len
    fk  = textstat.flesch_kincaid_grade(txt)
    data[key].append((avg, fk))

FK_MAX = {"TIMES_L1": 12.5, "TIMES_L2": 13.0, "TIMES_L3": 14.0}
AVG_MIN = {"TIMES_L1": 10.5, "TIMES_L2": 13.5, "TIMES_L3": 15.5}

print(f"\n  {'레벨':<12} {'n':>5}  {'avg_min':>7}  {'fk_max':>6}  "
      f"{'fk_p10':>6} {'fk_p50':>6} {'fk_p90':>6}  {'FK>fk_max':>10}")
print(f"  {'─'*12} {'─'*5}  {'─'*7}  {'─'*6}  {'─'*6} {'─'*6} {'─'*6}  {'─'*10}")

for key in ("TIMES_L1", "TIMES_L2", "TIMES_L3"):
    xs_fk  = [fk  for _, fk  in data[key]]
    if not xs_fk: continue
    p10f = pct(xs_fk, 10); p50f = pct(xs_fk, 50); p90f = pct(xs_fk, 90)
    over = sum(1 for v in xs_fk if v > FK_MAX[key])
    print(f"  {key:<12} {len(xs_fk):>5}  {AVG_MIN[key]:>7.1f}  {FK_MAX[key]:>6.1f}  "
          f"{p10f:>6.1f} {p50f:>6.1f} {p90f:>6.1f}  {over:>4}건({over/len(xs_fk)*100:.0f}%)")

# ── 2. "avg_min 통과 + FK 낮음" 규모 ─────────────────────────────────────
print()
print("=" * 72)
print("2. avg_min 통과 BUT FK 낮음 — 문장 길이는 맞는데 어휘 쉬운 기사")
print("   (fk_min 후보별: 몇 건이 추가로 걸리나)")
print("=" * 72)

# avg_min 통과 기사만 추출
for key in ("TIMES_L1", "TIMES_L2", "TIMES_L3"):
    passed_avg = [(avg, fk) for avg, fk in data[key] if avg >= AVG_MIN[key]]
    total = len(data[key])
    n_pass_avg = len(passed_avg)
    fks = [fk for _, fk in passed_avg]
    if not fks: continue

    print(f"\n  {key}  전체 {total}건 → avg_min({AVG_MIN[key]}) 통과 {n_pass_avg}건")
    print(f"  {'fk_min 후보':>12}  {'추가탈락건':>10}  {'추가탈락률':>10}  {'누적통과율'}")
    print(f"  {'─'*12}  {'─'*10}  {'─'*10}  {'─'*15}")
    prev_pass = n_pass_avg
    for cand in (5.0, 6.0, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0):
        reject = sum(1 for v in fks if v < cand)
        final_pass = n_pass_avg - reject
        print(f"  {cand:>12.1f}  {reject:>10}  {reject/n_pass_avg*100:>9.1f}%  "
              f"{final_pass}건 통과 ({final_pass/total*100:.0f}%)")

# ── 3. avg_min 통과 + FK 낮은 실제 기사 샘플 ─────────────────────────────
print()
print("=" * 72)
print("3. avg_min 통과 BUT FK < 8.0 기사 샘플 — 어휘 낮은 게 실제로 어떻게 생겼나")
print("=" * 72)

for key in ("TIMES_L1", "TIMES_L2", "TIMES_L3"):
    suspects = []
    for row in rows[1:]:
        if not row or len(row) <= max(lv_col, tx_col, sc_col): continue
        lv  = str(row[lv_col]).strip() if row[lv_col] else ""
        txt = str(row[tx_col]).strip() if row[tx_col] else ""
        sec = str(row[sc_col]).strip() if row[sc_col] else ""
        if not lv or len(txt) < 50: continue
        if sec in EXCLUDE_SECTIONS: continue
        wc = len(re.findall(r"[A-Za-z']+", txt))
        if wc < MIN_WC: continue
        m2 = re.search(r"\d+", lv)
        if not m2: continue
        if f"TIMES_L{m2.group()}" != key: continue
        if classify(txt, key).skip_cefr: continue
        avg = validate(txt, key).avg_sentence_len
        if avg < AVG_MIN[key]: continue          # avg_min 탈락 제외
        fk  = textstat.flesch_kincaid_grade(txt)
        if fk >= 8.0: continue                   # FK 낮은 것만
        suspects.append((avg, fk, sec, txt))
    suspects.sort(key=lambda x: x[1])            # FK 오름차순

    print(f"\n  ▶ {key}  avg_min 통과 + FK < 8.0  → {len(suspects)}건")
    if not suspects:
        print("    없음")
        continue
    print(f"  {'#':>3}  {'avg':>5}  {'FK':>5}  {'섹션':<20}  본문 앞 120자")
    print(f"  {'─'*3}  {'─'*5}  {'─'*5}  {'─'*20}  {'─'*50}")
    for i, (avg, fk, sec, txt) in enumerate(suspects[:10], 1):
        preview = txt[:120].replace("\n", " ")
        print(f"  {i:>3}  {avg:>5.1f}  {fk:>5.1f}  {sec:<20}  {preview}")
    if len(suspects) > 10:
        print(f"  ... 외 {len(suspects)-10}건")
