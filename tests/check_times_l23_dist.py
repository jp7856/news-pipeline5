"""TIMES L2/L3 avg_sentence_len 분포 + 하단 경계 샘플 — avg_min 보정용."""
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

TARGET_LEVELS = {
    "LEVEL 2": "TIMES_L2",
    "LEVEL 3": "TIMES_L3",
}

wb   = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws   = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
lv_col  = next(i for i,h in enumerate(hdr) if "레벨" in h or "level" in h.lower())
tx_col  = next(i for i,h in enumerate(hdr) if "본문" in h or "text" in h.lower())
sc_col  = next(i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower())
ttl_col = next((i for i,h in enumerate(hdr) if "제목" in h or "title" in h.lower()), None)

# key → [(avg, wc, sec, title, text)]
buckets: dict[str, list] = {"TIMES_L2": [], "TIMES_L3": []}

for row in rows[1:]:
    if not row or len(row) <= max(lv_col, tx_col): continue
    lv  = str(row[lv_col]).strip() if row[lv_col] else ""
    txt = str(row[tx_col]).strip() if row[tx_col] else ""
    sec = str(row[sc_col]).strip() if row[sc_col] else ""
    ttl = str(row[ttl_col]).strip() if (ttl_col and row[ttl_col]) else ""
    if lv not in TARGET_LEVELS: continue
    if sec in EXCLUDE_SECTIONS: continue
    wc = len(re.findall(r"[A-Za-z']+", txt))
    if wc < MIN_WC: continue

    key = TARGET_LEVELS[lv]
    cls = classify(txt, key)
    if cls.skip_cefr:
        continue  # BRIEF / DIALOGUE 제외

    r = validate(txt, key)
    buckets[key].append((r.avg_sentence_len, wc, sec, ttl, txt))


def pct(xs, p):
    s = sorted(xs)
    return s[min(int(len(s) * p / 100), len(s) - 1)]


def below(xs, threshold):
    return sum(1 for x in xs if x < threshold)


for key in ["TIMES_L2", "TIMES_L3"]:
    data = buckets[key]
    avgs = [a for a, *_ in data]
    spec = LEVELS[key]
    n    = len(avgs)

    print("=" * 70)
    print(f"{key}  n={n}  현행 avg_min={spec.avg_min}")
    print("=" * 70)

    print(f"\n  분위수 분포:")
    for p in [5, 10, 15, 20, 25, 50]:
        v = pct(avgs, p)
        marker = " ← avg_min" if abs(v - spec.avg_min) < 0.3 else ""
        print(f"    p{p:<3} = {v:>6.2f}{marker}")

    print(f"\n  avg_min 후보별 거부율:")
    for c in [12.0, 12.5, 13.0, 13.5, 14.0, 14.5, 15.0, 15.5, 16.0]:
        n_rej = below(avgs, c)
        rate  = n_rej / n * 100
        mark  = "  ← 현행" if c == spec.avg_min else ""
        print(f"    {c:>5.1f}  {n_rej:>5}건  {rate:>5.1f}%{mark}")

    # 하단 10개 샘플 — avg 낮은 순
    bottom10 = sorted(data, key=lambda x: x[0])[:10]
    print(f"\n  하단 10개 샘플 (avg 낮은 순):")
    print("  " + "─" * 66)
    for rank, (avg, wc, sec, ttl, txt) in enumerate(bottom10, 1):
        # 문장 5개까지 미리보기
        sentences = re.split(r'(?<=[.!?])\s+', txt.strip())
        preview = " ".join(sentences[:4])[:220]
        print(f"\n  [{rank}] avg={avg:.1f}  wc={wc}  섹션={sec}")
        print(f"       제목: {ttl[:72]}")
        print(f"       {preview}...")
    print()
