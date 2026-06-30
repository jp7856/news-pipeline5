"""TIMES_L2 C1+ 비율 섹션별 분포 (dedup_types=True)."""
import sys, io, re, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl
from agents.sub_agents.vocab_checker import measure
from agents.sub_agents.article_classifier import classify

XLSX_PATH  = r"C:\Users\jp\Desktop\기사\articles.xlsx"
YEAR_CUTOFF = 2024
_YEAR_RE   = re.compile(r'\b(20\d{2})\b')
_CCTV_RE   = re.compile(r'\b(?:CCTV|surveillance\s+camera|surveillance\s+infrastructure)\b',
                        re.IGNORECASE)

EXCLUDE_SECTIONS = {
    "Photo News", "Briefs", "Star Brief", "News in Brief",
    "Cartoon", "Did You Know", "Did You Know?",
    "Debating", "Cover", "Q & A",
    "NE You", "My Journal", "Book Review",
    "Stories", "Story", "Readings for Junior",
    "VoA Broadcast News", "Think About It", "My Diary", "Debate",
}

def pct(xs, p):
    if not xs:
        return float("nan")
    s = sorted(xs)
    return s[min(int(len(s) * p / 100), len(s) - 1)]

def percentile_of(val, xs):
    """val이 xs 분포에서 몇 분위인지 (0~100)."""
    if not xs:
        return float("nan")
    return round(sum(1 for x in xs if x <= val) / len(xs) * 100, 1)

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]

lv_col  = next((i for i,h in enumerate(hdr) if "레벨"  in h or "level"   in h.lower()), None)
tx_col  = next((i for i,h in enumerate(hdr) if "본문"  in h or "text"    in h.lower()), None)
sc_col  = next((i for i,h in enumerate(hdr) if "섹션"  in h or "section" in h.lower()), None)
dt_col  = next((i for i,h in enumerate(hdr) if "날짜"  in h or "date"    in h.lower()), None)
iss_col = next((i for i,h in enumerate(hdr) if "호수"  in h or "issue"   in h.lower()), None)

def gc(row, col):
    if col is None or len(row) <= col or row[col] is None:
        return ""
    return str(row[col]).strip()

# ── 2024+ ARTICLE 수집 ────────────────────────────────────────────────────────
# sec_data[section] = [c1plus_pct, ...]
sec_data: dict[str, list[float]] = collections.defaultdict(list)
total_processed = 0

print("분석 중...", end="", flush=True)

for row in rows[1:]:
    if not row:
        continue
    lv_raw = gc(row, lv_col)
    if re.sub(r'[^0-9]', '', lv_raw) != "2":
        continue

    sc = gc(row, sc_col)
    tx = gc(row, tx_col)
    dt = gc(row, dt_col)

    if sc in EXCLUDE_SECTIONS:
        continue

    ym = _YEAR_RE.search(dt)
    yr = int(ym.group()) if ym else None
    if yr is not None and yr < YEAR_CUTOFF:
        continue

    if not tx or len(tx) < 30:
        continue

    cls = classify(tx, "TIMES_L2")
    if cls.skip_cefr:
        continue

    res = measure(tx, dedup_types=True)
    sec_data[sc].append(res.c1plus_pct)
    total_processed += 1
    print(".", end="", flush=True)

print(f" 완료  (총 {total_processed}건)\n")

# ── 섹션별 분포 ───────────────────────────────────────────────────────────────
# 관심 섹션 표시 순서 (뉴스→피처→생활·문화)
ORDER = [
    "Headlines News",
    "World",
    "Key Issue",
    "Science",
    "Read and Learn",
    "Lifestyle",
    "Sports & Entertainment",
]
# ORDER에 없는 섹션은 마지막에 추가
extras = [s for s in sec_data if s not in ORDER]
all_sections = ORDER + sorted(extras)

print("─" * 70)
print("섹션별 C1+ 비율 분포 (TIMES_L2, dedup=True, 2024+)")
print("─" * 70)
print(f"  {'섹션':<26}  {'n':>4}  {'p50':>6}  {'p75':>6}  {'p90':>6}")
print(f"  {'-'*26}  {'-'*4}  {'-'*6}  {'-'*6}  {'-'*6}")

sec_p50: dict[str, float] = {}
for sec in all_sections:
    xs = sec_data.get(sec, [])
    if not xs:
        continue
    p50v = pct(xs, 50)
    p75v = pct(xs, 75)
    p90v = pct(xs, 90)
    sec_p50[sec] = p50v
    print(f"  {sec:<26}  {len(xs):>4}  {p50v:>5.1f}%  {p75v:>5.1f}%  {p90v:>5.1f}%")

# ── CCTV 767호 위치 ───────────────────────────────────────────────────────────
# 767호는 2020년 → 2024+ 풀에 없음. dedup 측정값 7.9%를 Science 2024+ 분포에 대입.
CCTV_767_DEDUP = 7.9
CCTV_767_SEC   = "Science"

print("\n" + "─" * 70)
print(f"CCTV 767호 위치 — 섹션: {CCTV_767_SEC}, dedup C1+={CCTV_767_DEDUP}%")
print("─" * 70)

sci_xs = sec_data.get(CCTV_767_SEC, [])
if sci_xs:
    pctile = percentile_of(CCTV_767_DEDUP, sci_xs)
    p90_sci = pct(sci_xs, 90)
    p75_sci = pct(sci_xs, 75)
    above_p90 = "★ p90 초과" if CCTV_767_DEDUP > p90_sci else (
                "p75~p90"  if CCTV_767_DEDUP > p75_sci else "p75 이하")
    print(f"  Science 2024+ 분포: n={len(sci_xs)}, p50={pct(sci_xs,50):.1f}%, "
          f"p75={p75_sci:.1f}%, p90={p90_sci:.1f}%")
    print(f"  CCTV 767호 {CCTV_767_DEDUP}% → Science 내 하위 {pctile}%  [{above_p90}]")

# 참고: 2024+ Science 기사 중 7.9% 이상은 몇 건?
above = [x for x in sci_xs if x >= CCTV_767_DEDUP]
print(f"  Science 2024+ 중 7.9% 이상: {len(above)}/{len(sci_xs)}건")
if above:
    print(f"  (해당 기사 값: {sorted(above)})")

# ── 참고: 섹션별 p50 비교 ──────────────────────────────────────────────────────
print("\n" + "─" * 70)
print("p50 기준 섹션 서열 (낮은 순)")
print("─" * 70)
ranked = sorted(
    [(s, pct(xs, 50), pct(xs, 90), len(xs))
     for s, xs in sec_data.items() if xs],
    key=lambda x: x[1],
)
for sec, p50v, p90v, n in ranked:
    bar = "█" * int(p50v)
    print(f"  {sec:<26}  p50={p50v:4.1f}%  p90={p90v:4.1f}%  n={n:3d}  {bar}")
