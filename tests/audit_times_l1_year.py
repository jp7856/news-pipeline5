"""TIMES_L1 발행연도별 분포 + avg_min 탈락 분포.
값 변경 없음 — 아카이브 오염 여부 확인 전용.
"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl
from agents.sub_agents.cefr_checker import LEVELS
from agents.sub_agents.article_classifier import classify

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"
EXCL = {
    "Photo News","Briefs","Star Brief","News in Brief","Cartoon",
    "Did You Know","Did You Know?","Debating","Cover","Q & A","NE You",
    "My Journal","Book Review","Stories","Story",
    "Readings for Junior","VoA Broadcast News","Think About It","My Diary","Pros & Cons",
}

_SE = re.compile(r"(?<=[.!?])\s+")
def avg_sl(t: str) -> float:
    p = [len(re.findall(r"[A-Za-z']+", s)) for s in _SE.split(t.strip())]
    p = [w for w in p if w >= 1]
    return sum(p) / len(p) if p else 0.0

def pct(xs, p):
    s = sorted(xs)
    if not s: return 0.0
    idx = (len(s)-1)*p/100
    lo = int(idx); hi = min(lo+1, len(s)-1)
    return s[lo] + (s[hi]-s[lo])*(idx-lo)

wb  = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws  = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]

# 헤더 확인
print("=== TIMES 시트 헤더 ===")
for i, h in enumerate(hdr):
    print(f"  [{i}] {h!r}")

lv_c  = next((i for i,h in enumerate(hdr) if "레벨"  in h or "level"   in h.lower()), None)
tx_c  = next((i for i,h in enumerate(hdr) if "본문"  in h or "text"    in h.lower()), None)
sc_c  = next((i for i,h in enumerate(hdr) if "섹션"  in h or "section" in h.lower()), None)
# 날짜·호수 컬럼 탐색
dt_c  = next((i for i,h in enumerate(hdr) if "날짜"  in h or "date"    in h.lower()), None)
iss_c = next((i for i,h in enumerate(hdr) if "호수"  in h or "issue"   in h.lower()), None)

print(f"\nlv={lv_c} tx={tx_c} sc={sc_c} date={dt_c} issue={iss_c}\n")

# 연도 추출 함수: 날짜 문자열 또는 호수에서 연도 파싱
_YEAR_RE = re.compile(r"\b(20\d{2}|19\d{2})\b")

def extract_year(row):
    # 날짜 컬럼 우선
    if dt_c is not None and row[dt_c]:
        v = str(row[dt_c]).strip()
        m = _YEAR_RE.search(v)
        if m: return int(m.group())
    # 호수 컬럼 — 정수면 호수 번호, 연도 아님
    # (호수→연도 변환은 불가하므로 날짜 컬럼만 사용)
    return None

AVG_MIN = LEVELS["TIMES_L1"].avg_min   # 10.5
RECENT_CUTOFF = 2022                   # 2022 이후 = 최근 3년 (2022~2024)

# year → {avgs: [], failed: int}
year_data: dict[int, dict] = {}
no_year_avgs: list = []
no_year_failed: int = 0

for row in rows[1:]:
    if not row or len(row) <= max(lv_c, tx_c): continue
    lval = str(row[lv_c]).strip() if row[lv_c] else ""
    txt  = str(row[tx_c]).strip() if row[tx_c] else ""
    sec  = str(row[sc_c]).strip() if (sc_c and row[sc_c]) else ""
    if not lval or len(txt) < 50 or sec in EXCL: continue
    if len(re.findall(r"[A-Za-z']+", txt)) < 100: continue
    m = re.search(r"\d+", lval)
    if not m or m.group() != "1": continue
    cls = classify(txt, "TIMES_L1")
    if cls.skip_cefr: continue
    avg = avg_sl(txt)
    if avg < 1.0: continue

    yr = extract_year(row)
    failed = avg < AVG_MIN

    if yr is None:
        no_year_avgs.append(avg)
        if failed: no_year_failed += 1
    else:
        bucket = year_data.setdefault(yr, {"avgs": [], "failed": 0})
        bucket["avgs"].append(avg)
        if failed: bucket["failed"] += 1

# ── 출력 1: 연도별 건수 ──────────────────────────────────────────────────
print("=" * 60)
print("TIMES_L1 ARTICLE — 연도별 건수 (발행일 컬럼 기준)")
print("=" * 60)
print(f"{'연도':>6}  {'건수':>6}  {'탈락':>6}  {'탈락률':>6}")
print("─" * 40)
for yr in sorted(year_data.keys()):
    b = year_data[yr]
    n = len(b["avgs"]); f = b["failed"]
    print(f"{yr:>6}  {n:>6}  {f:>6}  {f/n*100:>5.1f}%")
if no_year_avgs:
    n = len(no_year_avgs); f = no_year_failed
    print(f"{'(날짜없음)':>6}  {n:>6}  {f:>6}  {f/n*100:>5.1f}%")

# ── 출력 2: 최근 vs 이전 분포 ─────────────────────────────────────────
print()
print("=" * 60)
print(f"TIMES_L1 — 최근({RECENT_CUTOFF}~) vs 이전(~{RECENT_CUTOFF-1}) avg 분포")
print("=" * 60)

recent_avgs = []; recent_fail = 0
older_avgs  = []; older_fail  = 0
for yr, b in year_data.items():
    if yr >= RECENT_CUTOFF:
        recent_avgs.extend(b["avgs"]); recent_fail += b["failed"]
    else:
        older_avgs.extend(b["avgs"]);  older_fail  += b["failed"]
# 날짜없음은 별도
no_yr_label = f"날짜없음({len(no_year_avgs)}건)"

def show_dist(label, avgs, failed):
    n = len(avgs)
    if n == 0: print(f"{label}: 데이터 없음"); return
    print(f"\n{label}  n={n}  탈락={failed}({failed/n*100:.1f}%)")
    print(f"  p5={pct(avgs,5):.2f}  p25={pct(avgs,25):.2f}  p50={pct(avgs,50):.2f}"
          f"  p75={pct(avgs,75):.2f}  p95={pct(avgs,95):.2f}")

show_dist(f"최근({RECENT_CUTOFF}~)", recent_avgs, recent_fail)
show_dist(f"이전(~{RECENT_CUTOFF-1})", older_avgs, older_fail)
if no_year_avgs:
    show_dist(no_yr_label, no_year_avgs, no_year_failed)

# ── 출력 3: 탈락 760건의 연도별 분포 ────────────────────────────────────
print()
print("=" * 60)
print(f"avg_min({AVG_MIN}) 탈락 건수 — 연도별")
print("=" * 60)
total_fail = sum(b["failed"] for b in year_data.values()) + no_year_failed
print(f"탈락 총계: {total_fail}건")
print(f"{'연도':>6}  {'탈락건수':>8}  {'해당연도탈락률':>14}")
print("─" * 35)
for yr in sorted(year_data.keys()):
    b = year_data[yr]
    if b["failed"] == 0: continue
    n = len(b["avgs"]); f = b["failed"]
    print(f"{yr:>6}  {f:>8}  {f/n*100:>13.1f}%")
if no_year_failed:
    n = len(no_year_avgs)
    print(f"{'(없음)':>6}  {no_year_failed:>8}  {no_year_failed/n*100:>13.1f}%")
