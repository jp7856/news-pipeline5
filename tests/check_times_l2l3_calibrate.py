"""TIMES_L2 / L3 avg_min 보정 — 깨끗한 분포 + 하단 경계 샘플."""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import openpyxl
from agents.sub_agents.cefr_checker import validate, LEVELS
from agents.sub_agents.article_classifier import classify, ArticleType

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"
EXCLUDE_SECTIONS = {
    "Photo News", "Briefs", "Star Brief", "News in Brief",
    "Cartoon", "Did You Know", "Did You Know?", "Debating", "Cover", "Q & A",
    "NE You",
}
MIN_WC = 100

# ── 데이터 로드 ────────────────────────────────────────────────────────────
wb   = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws   = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
lv_col  = next(i for i,h in enumerate(hdr) if "레벨" in h or "level" in h.lower())
tx_col  = next(i for i,h in enumerate(hdr) if "본문" in h or "text" in h.lower())
sc_col  = next(i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower())
ttl_col = next((i for i,h in enumerate(hdr) if "제목" in h or "title" in h.lower()), None)

buckets: dict[str, list] = {"L2": [], "L3": []}  # (avg, sec, title, text)

for row in rows[1:]:
    if not row or len(row) <= max(lv_col, tx_col): continue
    lv  = str(row[lv_col]).strip() if row[lv_col] else ""
    txt = str(row[tx_col]).strip() if row[tx_col] else ""
    sec = str(row[sc_col]).strip() if row[sc_col] else ""
    ttl = str(row[ttl_col]).strip() if (ttl_col and row[ttl_col]) else ""
    if sec in EXCLUDE_SECTIONS: continue
    wc = len(re.findall(r"[A-Za-z']+", txt))
    if wc < MIN_WC: continue

    if lv == "LEVEL 2":
        key_level = "L2"
        cefr_key  = "TIMES_L2"
    elif lv == "LEVEL 3":
        key_level = "L3"
        cefr_key  = "TIMES_L3"
    else:
        continue

    cls = classify(txt, cefr_key)
    if cls.skip_cefr:
        continue  # BRIEF / DIALOGUE 제외

    avg = validate(txt, cefr_key).avg_sentence_len
    buckets[key_level].append((avg, sec, ttl, txt))


def pct(xs, p):
    s = sorted(xs)
    return s[min(int(len(s) * p / 100), len(s) - 1)]


def below(xs, threshold):
    return sum(1 for x in xs if x < threshold)


# ═══════════════════════════════════════════════════════════════════════════
for lv_tag, cefr_key, label_below, range_below in [
    ("L2", "TIMES_L2", "TIMES_L1", "avg 10.5~19.0"),
    ("L3", "TIMES_L3", "TIMES_L2", "avg 14.5~19.5"),
]:
    data = buckets[lv_tag]
    avgs = [a for a, *_ in data]
    spec = LEVELS[cefr_key]
    cur_min = spec.avg_min

    print("=" * 70)
    print(f"TIMES_{lv_tag}  (n={len(avgs)})  현행 avg_min={cur_min}")
    print(f"비교 기준: {label_below} 범위 = {range_below}")
    print("=" * 70)

    print(f"\n  avg percentile (BRIEF/DIALOGUE 제외 후):")
    for p in [5, 10, 15, 20, 25, 50]:
        val = pct(avgs, p)
        flag = "  ← 현행 avg_min" if abs(val - cur_min) < 0.3 else ""
        print(f"    p{p:<3}  {val:>6.2f}{flag}")

    print(f"\n  avg_min 후보별 거부율:")
    for c in [13.0, 13.5, 14.0, 14.5, 15.0, 15.5, 16.0]:
        if lv_tag == "L3" and c < 14.5: continue
        n    = below(avgs, c)
        rate = n / len(avgs) * 100
        mark = "  ← 현행" if c == cur_min else ""
        print(f"    {c:>5.1f}  {n:>6}건  {rate:>5.1f}%{mark}")

    # 하단 경계 샘플 — p5~p15 구간 기사를 avg 오름차순으로
    p5_val  = pct(avgs, 5)
    p15_val = pct(avgs, 15)
    low_samples = sorted(
        [(a, s, t, tx) for a, s, t, tx in data if p5_val <= a <= p15_val],
        key=lambda x: x[0]
    )[:10]

    print(f"\n  하단 경계 샘플 (avg p5~p15: {p5_val:.1f}~{p15_val:.1f}) — {len(low_samples)}건")
    print(f"  {'avg':>6}  {'섹션':<22} {'본문 첫 150자'}")
    print("  " + "─" * 80)
    for avg_v, sec, ttl, txt in low_samples:
        preview = txt[:150].replace("\n", " ")
        print(f"  {avg_v:>6.2f}  {sec:<22} {preview}...")
    print()
