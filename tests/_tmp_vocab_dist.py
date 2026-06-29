"""TIMES_L2 현행 ARTICLE 풀 C1+ 어휘 비율 분포 (dedup_types=True 정밀화 버전)."""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl
from agents.sub_agents.vocab_checker import measure
from agents.sub_agents.article_classifier import classify

XLSX_PATH  = r"C:\Users\jp\Desktop\기사\articles.xlsx"
YEAR_CUTOFF = 2024
_YEAR_RE   = re.compile(r'\b(20\d{2})\b')
_FIRST_200 = re.compile(r'^[\s\S]{0,200}')

EXCLUDE_SECTIONS = {
    "Photo News", "Briefs", "Star Brief", "News in Brief",
    "Cartoon", "Did You Know", "Did You Know?",
    "Debating", "Cover", "Q & A",
    "NE You", "My Journal", "Book Review",
    "Stories", "Story", "Readings for Junior",
    "VoA Broadcast News", "Think About It", "My Diary", "Debate",
}

# CCTV 검색 (연도 무관 전체 코퍼스용)
_CCTV_RE = re.compile(
    r'\b(?:CCTV|surveillance\s+camera|surveillance\s+infrastructure'
    r'|security\s+camera|closed[- ]circuit)\b',
    re.IGNORECASE,
)

def pct(xs, p):
    if not xs:
        return 0.0
    s = sorted(xs)
    return s[min(int(len(s) * p / 100), len(s) - 1)]

def load_times_sheet():
    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
    ws = wb["TIMES"]
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(c).strip() if c else "" for c in rows[0]]
    cols = {
        "lv":  next((i for i,h in enumerate(hdr) if "레벨"  in h or "level"   in h.lower()), None),
        "tx":  next((i for i,h in enumerate(hdr) if "본문"  in h or "text"    in h.lower()), None),
        "sc":  next((i for i,h in enumerate(hdr) if "섹션"  in h or "section" in h.lower()), None),
        "dt":  next((i for i,h in enumerate(hdr) if "날짜"  in h or "date"    in h.lower()), None),
        "iss": next((i for i,h in enumerate(hdr) if "호수"  in h or "issue"   in h.lower()), None),
    }
    return rows, cols

def get_cell(row, col):
    if col is None or len(row) <= col or row[col] is None:
        return ""
    return str(row[col]).strip()

# ── 1. TIMES_L2 2024+ ARTICLE 풀 분석 (dedup_types=True) ─────────────────────
rows, cols = load_times_sheet()

# (c1pct, c1_only, c2_only, sc, prev200, total_w, c1_cnt, c2_cnt, iss, dt)
results: list[tuple] = []
skip = {"EXCLUDE_SEC": 0, "YEAR": 0, "BRIEF": 0, "DIALOGUE": 0}
total_l2 = 0

print("분석 중 (dedup=ON)...", end="", flush=True)

for row in rows[1:]:
    if not row:
        continue
    lv_raw = get_cell(row, cols["lv"])
    if re.sub(r'[^0-9]', '', lv_raw) != "2":
        continue
    total_l2 += 1

    sc = get_cell(row, cols["sc"])
    tx = get_cell(row, cols["tx"])
    dt = get_cell(row, cols["dt"])
    iss = get_cell(row, cols["iss"])

    if sc in EXCLUDE_SECTIONS:
        skip["EXCLUDE_SEC"] += 1
        continue

    yr = None
    if dt:
        ym = _YEAR_RE.search(dt)
        if ym:
            yr = int(ym.group())
    if yr is not None and yr < YEAR_CUTOFF:
        skip["YEAR"] += 1
        continue

    if not tx or len(tx) < 30:
        continue

    cls = classify(tx, "TIMES_L2")
    if cls.skip_cefr:
        key = "BRIEF" if cls.article_type.value == "BRIEF" else "DIALOGUE"
        skip[key] += 1
        continue

    res = measure(tx, dedup_types=True)
    denom  = res.total_words
    c1pct  = res.c1plus_pct
    c1_only = round(res.c1_count / denom * 100, 1) if denom else 0.0
    c2_only = round(res.c2_count / denom * 100, 1) if denom else 0.0
    prev200 = tx.strip()[:200].replace("\n", " ")

    results.append((c1pct, c1_only, c2_only, sc, prev200, denom, res.c1_count, res.c2_count, iss, dt))
    print(".", end="", flush=True)

print(" 완료\n")

# ── 분포 출력 ────────────────────────────────────────────────────────────────
n = len(results)
print(f"TIMES L2 전체: {total_l2}건")
print(f"제외 — 섹션EXCL={skip['EXCLUDE_SEC']}, 연도<{YEAR_CUTOFF}: {skip['YEAR']}, "
      f"BRIEF={skip['BRIEF']}, DIALOGUE={skip['DIALOGUE']}")
print(f"분석 대상: {n}건\n")

if not results:
    print("결과 없음")
    sys.exit(0)

ratios    = [r[0] for r in results]
c1_ratios = [r[1] for r in results]
c2_ratios = [r[2] for r in results]

print("─" * 58)
print("C1+ 비율 분포 (dedup_types=True, 반복 부풀림 제거)")
print("─" * 58)
print(f"  {'':6}  {'C1+':>7}  {'C1만':>7}  {'C2만':>7}")
for label, p in [("p10",10),("p25",25),("p50",50),("p75",75),("p90",90),("p95",95)]:
    print(f"  {label:6}  {pct(ratios,p):7.1f}%  {pct(c1_ratios,p):7.1f}%  {pct(c2_ratios,p):7.1f}%")
avg = sum(ratios) / n
print(f"  {'avg':6}  {avg:7.1f}%")
print(f"  {'min':6}  {min(ratios):7.1f}%")
print(f"  {'max':6}  {max(ratios):7.1f}%")

# ── 2. p90 이상 상위 10건 ─────────────────────────────────────────────────────
sorted_r = sorted(results, key=lambda x: x[0])
top10    = sorted_r[-10:]

print("\n" + "─" * 70)
print("C1+ 상위 10건 (높은 순, dedup 적용)")
print("─" * 70)
for rank, (c1pct, c1o, c2o, sc, prev, total, c1, c2, iss, dt) in enumerate(reversed(top10), 1):
    print(f"\n#{rank}  C1+={c1pct:.1f}%  C1={c1o:.1f}%  C2={c2o:.1f}%  "
          f"types={total}  섹션=[{sc}]  {iss} {dt}")
    print(f"    {prev[:200]}")

# ── 3. CCTV 기사 — 전체 코퍼스에서 재측정 (dedup=True) ───────────────────────
print("\n" + "─" * 70)
print("CCTV/surveillance 기사 — 전체 코퍼스 dedup 측정")
print("─" * 70)

cctv_rows = []
for row in rows[1:]:
    if not row:
        continue
    lv_raw = get_cell(row, cols["lv"])
    if re.sub(r'[^0-9]', '', lv_raw) != "2":
        continue
    tx  = get_cell(row, cols["tx"])
    sc  = get_cell(row, cols["sc"])
    dt  = get_cell(row, cols["dt"])
    iss = get_cell(row, cols["iss"])
    if not _CCTV_RE.search(tx):
        continue
    if sc in EXCLUDE_SECTIONS:
        continue
    cls = classify(tx, "TIMES_L2")
    if cls.skip_cefr:
        continue
    res_tok = measure(tx, dedup_types=False)   # 토큰 기준 (이전 지표)
    res_dup = measure(tx, dedup_types=True)    # dedup 기준 (새 지표)
    prev = tx.strip()[:200].replace("\n", " ")
    cctv_rows.append((res_tok.c1plus_pct, res_dup.c1plus_pct, sc, dt, iss, prev))

cctv_rows.sort(key=lambda x: x[0])
print(f"{len(cctv_rows)}건 발견\n")
print(f"  {'호수/날짜':<30}  {'토큰C1+':>8}  {'dedupC1+':>9}  섹션")
print(f"  {'-'*30}  {'-'*8}  {'-'*9}  ----")
for tok_pct, dup_pct, sc, dt, iss, prev in cctv_rows:
    print(f"  {(iss + ' ' + dt):<30}  {tok_pct:8.1f}%  {dup_pct:9.1f}%  [{sc}]")

print("\n본문 앞 200자 (C1+ 높은 순):")
for tok_pct, dup_pct, sc, dt, iss, prev in sorted(cctv_rows, key=lambda x: -x[0])[:6]:
    print(f"\n  토큰={tok_pct:.1f}% → dedup={dup_pct:.1f}%  [{iss}]")
    print(f"  {prev}")

# ── 4. CCTV 기사의 2024+ 상위권 내 위치 ─────────────────────────────────────
print("\n" + "─" * 70)
print("CCTV 기사 위치 (2024+ 풀 기준, 백분위)")
print("─" * 70)
# p90 threshold
p90_val = pct(ratios, 90)
print(f"2024+ 풀 p90 = {p90_val:.1f}%")
for tok_pct, dup_pct, sc, dt, iss, prev in cctv_rows:
    rank_pos = sum(1 for r in ratios if r <= dup_pct)
    pctile   = round(rank_pos / n * 100, 1)
    above_p90 = "★ p90 이상" if dup_pct >= p90_val else ""
    print(f"  [{iss} {dt}]  dedup={dup_pct:.1f}%  → {n}건 중 하위 {pctile}%  {above_p90}")
