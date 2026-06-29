"""TIMES_L2 현행 ARTICLE 풀 C1+ 어휘 비율 분포 확인."""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl
from agents.sub_agents.vocab_checker import measure
from agents.sub_agents.article_classifier import classify

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"
YEAR_CUTOFF = 2024
_YEAR_RE = re.compile(r'\b(20\d{2})\b')

EXCLUDE_SECTIONS = {
    "Photo News", "Briefs", "Star Brief", "News in Brief",
    "Cartoon", "Did You Know", "Did You Know?",
    "Debating", "Cover", "Q & A",
    "NE You", "My Journal", "Book Review",
    "Stories", "Story", "Readings for Junior",
    "VoA Broadcast News", "Think About It", "My Diary", "Debate",
}

# CCTV/감시카메라 관련 기사 검색용
_CCTV_RE = re.compile(
    r'\b(?:CCTV|surveillance\s+camera|surveillance\s+infrastructure'
    r'|security\s+camera|closed[- ]circuit)\b',
    re.IGNORECASE,
)
# 제목 컬럼이 잡음이므로 본문 첫 문장을 미리보기로 사용
_FIRST_SENT = re.compile(r'^[^.!?]+[.!?]')

def preview(tx: str) -> str:
    m = _FIRST_SENT.match(tx.strip())
    return (m.group(0) if m else tx[:80]).strip()

def pct(xs, p):
    if not xs:
        return 0.0
    s = sorted(xs)
    return s[min(int(len(s) * p / 100), len(s) - 1)]

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr = [str(c).strip() if c else "" for c in rows[0]]

lv_col = next((i for i,h in enumerate(hdr) if "레벨"  in h or "level"   in h.lower()), None)
tx_col = next((i for i,h in enumerate(hdr) if "본문"  in h or "text"    in h.lower()), None)
sc_col = next((i for i,h in enumerate(hdr) if "섹션"  in h or "section" in h.lower()), None)
dt_col = next((i for i,h in enumerate(hdr) if "날짜"  in h or "date"    in h.lower()), None)

if lv_col is None or tx_col is None:
    print(f"컬럼 감지 실패 — 헤더: {hdr}")
    sys.exit(1)

# (c1plus_pct, c1_only_pct, c2_only_pct, prev, total_words, c1_cnt, c2_cnt, tx)
results: list[tuple] = []
cctv_hits: list[tuple] = []
skip = {"EXCLUDE_SEC": 0, "YEAR": 0, "BRIEF": 0, "DIALOGUE": 0}
total_l2 = 0

print("분석 중...", end="", flush=True)

for row in rows[1:]:
    if not row:
        continue
    needed = [c for c in [lv_col, tx_col, sc_col, dt_col] if c is not None]
    if needed and len(row) <= max(needed):
        continue

    lv_raw = str(row[lv_col]).strip() if row[lv_col] else ""
    if re.sub(r'[^0-9]', '', lv_raw) != "2":
        continue
    total_l2 += 1

    sc = str(row[sc_col]).strip() if sc_col is not None and row[sc_col] else ""
    tx = str(row[tx_col]).strip() if row[tx_col] else ""

    if sc in EXCLUDE_SECTIONS:
        skip["EXCLUDE_SEC"] += 1
        continue

    yr = None
    if dt_col is not None and len(row) > dt_col and row[dt_col]:
        ym = _YEAR_RE.search(str(row[dt_col]))
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

    res = measure(tx)
    denom = res.total_words
    c1pct  = res.c1plus_pct
    c1_only = round(res.c1_count / denom * 100, 1) if denom > 0 else 0.0
    c2_only = round(res.c2_count / denom * 100, 1) if denom > 0 else 0.0
    prev = preview(tx)[:80]

    entry = (c1pct, c1_only, c2_only, prev, denom, res.c1_count, res.c2_count, tx)
    results.append(entry)

    if _CCTV_RE.search(tx):
        cctv_hits.append(entry)

    print(".", end="", flush=True)

print(" 완료\n")

print(f"TIMES L2 전체: {total_l2}건")
print(f"제외 — 섹션EXCL={skip['EXCLUDE_SEC']}, 연도<{YEAR_CUTOFF}: {skip['YEAR']}, "
      f"BRIEF={skip['BRIEF']}, DIALOGUE={skip['DIALOGUE']}")
print(f"분석 대상: {len(results)}건\n")

if not results:
    print("결과 없음")
    sys.exit(0)

ratios    = [r[0] for r in results]
c1_ratios = [r[1] for r in results]
c2_ratios = [r[2] for r in results]

print("─" * 58)
print("C1+ 비율 분포 (TIMES_L2 현행 ARTICLE 풀)")
print("─" * 58)
print(f"  {'':6}  {'C1+':>7}  {'C1만':>7}  {'C2만':>7}")
for label, p in [("p10",10),("p25",25),("p50",50),("p75",75),("p90",90),("p95",95)]:
    print(f"  {label:6}  {pct(ratios,p):7.1f}%  {pct(c1_ratios,p):7.1f}%  {pct(c2_ratios,p):7.1f}%")
avg = sum(ratios) / len(ratios)
print(f"  {'avg':6}  {avg:7.1f}%")
print(f"  {'min':6}  {min(ratios):7.1f}%")
print(f"  {'max':6}  {max(ratios):7.1f}%")

sorted_r = sorted(results, key=lambda x: x[0])
print("\n하위 5건 (C1+ 낮음):")
for c1pct, c1o, c2o, prev, total, c1, c2, _ in sorted_r[:5]:
    print(f"  {c1pct:5.1f}%  C1={c1o:.1f}% C2={c2o:.1f}%  w={total}  {prev}")

print("\n상위 5건 (C1+ 높음):")
for c1pct, c1o, c2o, prev, total, c1, c2, _ in sorted_r[-5:]:
    print(f"  {c1pct:5.1f}%  C1={c1o:.1f}% C2={c2o:.1f}%  w={total}  {prev}")

# ── CCTV 기사 ─────────────────────────────────────────────────────────────────
print("\n" + "─" * 58)
print("CCTV / surveillance camera 키워드 본문 매칭 기사")
print("─" * 58)
if cctv_hits:
    print(f"  {len(cctv_hits)}건 발견")
    for c1pct, c1o, c2o, prev, total, c1, c2, _ in sorted(cctv_hits, key=lambda x: x[0]):
        print(f"\n  C1+={c1pct:.1f}%  (C1={c1o:.1f}% / C2={c2o:.1f}%)  total_words={total}")
        print(f"  [{prev}]")
else:
    print("  없음 — 'surveillance' 단독으로 재검색:")
    surv_re = re.compile(r'\bsurveillance\b', re.IGNORECASE)
    surv_hits = [(c1pct,c1o,c2o,prev,tot,c1,c2)
                 for c1pct,c1o,c2o,prev,tot,c1,c2,tx in results
                 if surv_re.search(tx)]
    if surv_hits:
        for c1pct, c1o, c2o, prev, tot, c1, c2 in sorted(surv_hits, key=lambda x: x[0]):
            print(f"  C1+={c1pct:.1f}%  (C1={c1o:.1f}% C2={c2o:.1f}%)  w={tot}  {prev}")
    else:
        print("  surveillance 키워드도 없음")
