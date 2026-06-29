"""avg_min 게이트 전 매체 검증.

확정된 EXCLUDE 규칙 적용 후 ARTICLE 풀 기준으로,
avg_min 통과/탈락 건수·탈락률 + 탈락 샘플 3개씩 출력.
값 변경 없음 — 현 게이트 실측 확인 전용.
"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl
from agents.sub_agents.cefr_checker import LEVELS
from agents.sub_agents.article_classifier import classify

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"

# ── 확정 EXCLUDE 규칙 ────────────────────────────────────────────────────────
EXCLUDE_SECTIONS = {
    "Photo News", "Briefs", "Star Brief", "News in Brief",
    "Cartoon", "Did You Know", "Did You Know?",
    "Debating", "Cover", "Q & A",
    "NE You",
    "My Journal", "Book Review",
    "Stories", "Story",
    "Readings for Junior",
    "VoA Broadcast News",
    "Think About It",   # KINDER 토론/의견나열 포맷
    "My Diary",         # KINDER 1인칭 일기체
    # Speak Out: 섹션 단위 제외 금지 — classifier DIALOGUE 판정만 제외
}

SHEET_CFG = {
    "KINDER":   ("KINDER",   0),
    "KIDS":     ("KIDS",    50),
    "JUNIOR":   ("JUNIOR",  80),
    "JUNIOR M": ("JUNIORM", 100),
    "TIMES":    ("TIMES",   100),
}

_SENT_END = re.compile(r'(?<=[.!?])\s+')
_YEAR_RE  = re.compile(r'\b(20\d{2})\b')
YEAR_CUTOFF = 2024

def avg_sent_len(text: str) -> float:
    parts = _SENT_END.split(text.strip())
    wcs   = [len(re.findall(r"[A-Za-z']+", p)) for p in parts]
    wcs   = [w for w in wcs if w >= 1]
    return sum(wcs) / len(wcs) if wcs else 0.0

ORDER = [
    "KINDER_L1", "KINDER_L2",
    "KIDS_L1",   "KIDS_L2",   "KIDS_L3",
    "JUNIOR_L1", "JUNIOR_L2", "JUNIOR_L3",
    "JUNIORM_L1","JUNIORM_L2",
    "TIMES_L1",  "TIMES_L2",  "TIMES_L3",
]

# ── 수집 ────────────────────────────────────────────────────────────────────
# key → {total: int, passed: [(ttl, avg, txt)], failed: [(ttl, avg, txt)]}
results: dict[str, dict] = {}

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)

for sheet_name, (prefix, min_wc) in SHEET_CFG.items():
    ws   = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    hdr  = [str(c).strip() if c else "" for c in rows[0]]
    lv_col  = next((i for i,h in enumerate(hdr) if "레벨"  in h or "level"   in h.lower()), None)
    tx_col  = next((i for i,h in enumerate(hdr) if "본문"  in h or "text"    in h.lower()), None)
    sc_col  = next((i for i,h in enumerate(hdr) if "섹션"  in h or "section" in h.lower()), None)
    ttl_col = next((i for i,h in enumerate(hdr) if "제목"  in h or "title"   in h.lower()), None)
    dt_col  = next((i for i,h in enumerate(hdr) if "날짜"  in h or "date"    in h.lower()), None)
    if lv_col is None or tx_col is None:
        continue

    for row in rows[1:]:
        if not row or len(row) <= max(lv_col, tx_col):
            continue
        lv  = str(row[lv_col]).strip()  if row[lv_col]  else ""
        txt = str(row[tx_col]).strip()  if row[tx_col]  else ""
        sec = str(row[sc_col]).strip()  if (sc_col  and row[sc_col])  else ""
        ttl = str(row[ttl_col]).strip() if (ttl_col and row[ttl_col]) else ""
        if not lv or len(txt) < 50:
            continue
        if sec in EXCLUDE_SECTIONS:
            continue
        wc = len(re.findall(r"[A-Za-z']+", txt))
        if wc < min_wc:
            continue
        m = re.search(r"\d+", lv)
        if not m:
            continue
        if int(m.group()) == 0:
            continue                             # KIDS L0 아카이브
        yr = None
        if dt_col is not None and len(row) > dt_col and row[dt_col]:
            ym = _YEAR_RE.search(str(row[dt_col]))
            if ym: yr = int(ym.group())
        if yr is not None and yr < YEAR_CUTOFF:
            continue                             # 아카이브 제외 (2024~ 현행 기준)
        key = f"{prefix}_L{m.group()}"
        if key not in LEVELS:
            continue
        if classify(txt, key).skip_cefr:
            continue                             # BRIEF / DIALOGUE 제외
        avg = avg_sent_len(txt)
        if avg < 1.0:
            continue
        bucket = results.setdefault(key, {"total": 0, "passed": [], "failed": []})
        bucket["total"] += 1
        if avg >= LEVELS[key].avg_min:
            bucket["passed"].append((ttl, avg, txt))
        else:
            bucket["failed"].append((ttl, avg, txt))

# ── 출력 ────────────────────────────────────────────────────────────────────
HDR = f"{'레벨':<13} {'ARTICLE':>8}  {'통과':>6}  {'탈락':>6}  {'탈락률':>6}  avg_min"
print(HDR)
print("─" * 60)
for key in ORDER:
    if key not in results:
        print(f"{key:<13}  (데이터 없음)")
        continue
    b      = results[key]
    n      = b["total"]
    passed = len(b["passed"])
    failed = len(b["failed"])
    rate   = failed / n * 100 if n else 0
    spec   = LEVELS[key]
    print(f"{key:<13}  {n:>8}  {passed:>6}  {failed:>6}  {rate:>5.1f}%  (avg_min={spec.avg_min})")

# ── 탈락 샘플 ────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("avg_min 탈락 샘플  (레벨별 최대 3개, avg 내림차순 — 경계에 가까운 것 먼저)")
print("=" * 70)

for key in ORDER:
    if key not in results:
        continue
    failed = results[key]["failed"]
    if not failed:
        print(f"\n{key}: 탈락 없음")
        continue
    # avg 내림차순 정렬 — 게이트 경계에 가장 가까운 것 먼저
    failed_sorted = sorted(failed, key=lambda x: -x[1])
    picks = failed_sorted[:3]
    spec  = LEVELS[key]
    print(f"\n{'─'*70}")
    print(f"{key}  (avg_min={spec.avg_min},  탈락 {len(failed)}건 중 상위 {len(picks)}개)")
    print(f"{'─'*70}")
    for i, (ttl, avg, txt) in enumerate(picks, 1):
        preview = txt[:200].replace("\n", " ")
        print(f"\n[{i}] avg={avg:.2f}  제목={ttl[:65] or '(없음)'}")
        print(f"     {preview}{'...' if len(txt)>200 else ''}")
