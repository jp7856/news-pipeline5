"""TIMES_L2 avg_min 통과 + FK<8.0 908건 분석 — 구간별 건수 / 경계 샘플 / 포맷 분포."""
import sys, io, re
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
}
AVG_MIN = 13.5

# ── 데이터 수집 ──────────────────────────────────────────────────────────────
wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
lv_col  = next(i for i,h in enumerate(hdr) if "레벨" in h or "level"   in h.lower())
tx_col  = next(i for i,h in enumerate(hdr) if "본문" in h or "text"    in h.lower())
sc_col  = next(i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower())
ttl_col = next((i for i,h in enumerate(hdr) if "제목" in h or "title"  in h.lower()), None)

suspects = []   # (fk, avg, sec, title, txt, fmt)
for row in rows[1:]:
    if not row or len(row) <= max(lv_col, tx_col, sc_col): continue
    lv  = str(row[lv_col]).strip()  if row[lv_col]  else ""
    txt = str(row[tx_col]).strip()  if row[tx_col]  else ""
    sec = str(row[sc_col]).strip()  if row[sc_col]  else ""
    ttl = str(row[ttl_col]).strip() if (ttl_col and row[ttl_col]) else ""
    if not lv or len(txt) < 50: continue
    if sec in EXCLUDE_SECTIONS: continue
    wc = len(re.findall(r"[A-Za-z']+", txt))
    if wc < 100: continue
    m = re.search(r"\d+", lv)
    if not m or f"TIMES_L{m.group()}" != "TIMES_L2": continue
    cls = classify(txt, "TIMES_L2")
    if cls.skip_cefr: continue
    avg = validate(txt, "TIMES_L2").avg_sentence_len
    if avg < AVG_MIN: continue
    fk = textstat.flesch_kincaid_grade(txt)
    if fk >= 8.0: continue
    suspects.append((fk, avg, sec, ttl, txt, cls.article_type.value))

suspects.sort(key=lambda x: x[0])
print(f"대상 총 {len(suspects)}건\n")

# ── 1. FK 구간별 건수 ────────────────────────────────────────────────────────
print("=" * 60)
print("1. FK 구간별 건수")
print("=" * 60)
BINS = [
    (float("-inf"), 6.0,  "4.9 – 6.0"),
    (6.0,           6.5,  "6.0 – 6.5"),
    (6.5,           7.0,  "6.5 – 7.0"),
    (7.0,           7.5,  "7.0 – 7.5"),
    (7.5,           8.0,  "7.5 – 8.0"),
]
for lo, hi, label in BINS:
    cnt = sum(1 for fk,*_ in suspects if lo <= fk < hi)
    bar = "█" * (cnt // 5)
    print(f"  {label}  {cnt:>4}건  {bar}")

# ── 2. FK 6.5–7.5 경계 샘플 10건 ────────────────────────────────────────────
print()
print("=" * 60)
print("2. FK 6.5–7.5 경계 샘플 10건  (FK 오름차순)")
print("=" * 60)
boundary = [(fk, avg, sec, ttl, txt, fmt)
            for fk, avg, sec, ttl, txt, fmt in suspects
            if 6.5 <= fk < 7.5]
step = max(1, len(boundary) // 10)
picks = [boundary[i] for i in range(0, min(len(boundary), step * 10), step)][:10]

for i, (fk, avg, sec, ttl, txt, fmt) in enumerate(picks, 1):
    preview = txt[:200].replace("\n", " ")
    print(f"\n[{i}]  FK={fk:.2f}  avg={avg:.1f}  섹션={sec}  포맷={fmt}")
    print(f"    제목: {ttl[:80] or '(없음)'}")
    print(f"    본문: {preview}{'...' if len(txt)>200 else ''}")

# ── 3. 포맷 분포 ─────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("3. 908건 classifier 포맷 분포")
print("=" * 60)
fmt_count: dict[str, int] = {}
for *_, fmt in suspects:
    fmt_count[fmt] = fmt_count.get(fmt, 0) + 1
for fmt, cnt in sorted(fmt_count.items(), key=lambda x: -x[1]):
    pct = cnt / len(suspects) * 100
    print(f"  {fmt:<12}  {cnt:>4}건  ({pct:.1f}%)")
