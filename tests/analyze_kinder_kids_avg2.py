"""KINDER/KIDS avg_sentence_len 분포 v2.

변경:
  - KIDS "LEVEL 0" 행 전부 제외 (레벨 라벨 기준).
  - KINDER 시트 이상 라벨·섹션 점검 후 보고 (자동 제외 없음).
필터 기준 (기존 동일):
  1. EXCLUDE_SECTIONS (사진·단신·포맷 섹션)
  2. classify().skip_cefr == True 제외 (BRIEF·DIALOGUE)
  3. 영단어 5개 미만 제거
"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl
from agents.sub_agents.article_classifier import classify

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"

EXCLUDE_SECTIONS = {
    "Photo News",
    "NE You",
    "Cover",
    "Did You Know", "Did You Know?",
    "Debating",
    "Q & A",
    "Cartoon",
}

_SENT_END = re.compile(r'(?<=[.!?])\s+')

def avg_sent_len(text: str) -> float:
    parts = _SENT_END.split(text.strip())
    wcs = [len(re.findall(r"[A-Za-z']+", p)) for p in parts]
    wcs = [w for w in wcs if w >= 1]
    return sum(wcs) / len(wcs) if wcs else 0.0

def pct(d_sorted: list, p: float) -> float:
    if not d_sorted: return 0.0
    idx = (len(d_sorted) - 1) * p / 100
    lo = int(idx)
    hi = min(lo + 1, len(d_sorted) - 1)
    return d_sorted[lo] + (d_sorted[hi] - d_sorted[lo]) * (idx - lo)

# ── 헬퍼: 시트 로드 ───────────────────────────────────────────────────────
def load_sheet(sheet_name: str):
    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    hdr  = [str(c).strip() if c else "" for c in rows[0]]
    lv_col  = next(i for i,h in enumerate(hdr) if "레벨" in h or "level"   in h.lower())
    tx_col  = next(i for i,h in enumerate(hdr) if "본문" in h or "text"    in h.lower())
    sc_col  = next((i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower()), None)
    ttl_col = next((i for i,h in enumerate(hdr) if "제목" in h or "title"   in h.lower()), None)
    dt_col  = next((i for i,h in enumerate(hdr) if "날짜" in h or "date"    in h.lower()), None)
    issue_col = next((i for i,h in enumerate(hdr) if "호수" in h or "issue" in h.lower()), None)
    return rows[1:], hdr, lv_col, tx_col, sc_col, ttl_col, dt_col, issue_col


# ══════════════════════════════════════════════════════════════════════════
# 1. KINDER 점검 — 이상 라벨·섹션 보고
# ══════════════════════════════════════════════════════════════════════════
print("=" * 70)
print("KINDER 시트 이상 라벨·섹션 점검")
print("=" * 70)

rows_k, hdr_k, lv_k, tx_k, sc_k, ttl_k, dt_k, iss_k = load_sheet("KINDER")

# 모든 레벨 값 수집
lv_counts_k: dict[str, int] = {}
for row in rows_k:
    if not row: continue
    lv = str(row[lv_k]).strip() if row[lv_k] else "(비어있음)"
    lv_counts_k[lv] = lv_counts_k.get(lv, 0) + 1

print("\n레벨 값 분포:")
for lv, cnt in sorted(lv_counts_k.items(), key=lambda x: -x[1]):
    print(f"  {lv!r:<20} {cnt}건")

# 섹션 전체 목록
sec_counts_k: dict[str, int] = {}
for row in rows_k:
    if not row or sc_k is None: continue
    sec = str(row[sc_k]).strip() if row[sc_k] else "(없음)"
    sec_counts_k[sec] = sec_counts_k.get(sec, 0) + 1

# 현행 KINDER 섹션 (basic.xlsx 분석 기준 — 알려진 것)
KNOWN_KINDER_SECTIONS = {
    "World", "Korea", "Science", "Animals", "People", "Culture",
    "Fun Facts", "Health", "Sports", "Environment", "Technology",
    "Animals & Nature", "Nature",
    "Photo News", "Did You Know", "Did You Know?", "Cover", "NE You",
}
unknown_secs = {s: c for s, c in sec_counts_k.items() if s not in KNOWN_KINDER_SECTIONS}

print(f"\n전체 섹션 목록 (총 {len(sec_counts_k)}종):")
for sec, cnt in sorted(sec_counts_k.items(), key=lambda x: -x[1]):
    flag = " ◀ 비현행" if sec not in KNOWN_KINDER_SECTIONS else ""
    print(f"  {sec!r:<30} {cnt}건{flag}")

# 비정상 라벨 행 샘플 (LEVEL 0, 비어있음, 기타)
anomaly_rows = []
for row in rows_k:
    if not row: continue
    lv = str(row[lv_k]).strip() if row[lv_k] else ""
    m = re.search(r"\d+", lv)
    level_num = int(m.group()) if m else -1
    if level_num not in (1, 2, 3):   # L1/L2/L3 이외
        anomaly_rows.append((lv, row))

if anomaly_rows:
    print(f"\n비정상 레벨 라벨 행 {len(anomaly_rows)}건 — 샘플 5건:")
    import random; random.seed(42)
    for lv, row in random.sample(anomaly_rows, min(5, len(anomaly_rows))):
        txt  = str(row[tx_k]).strip()  if row[tx_k]  else ""
        sec  = str(row[sc_k]).strip()  if (sc_k  and row[sc_k])  else ""
        ttl  = str(row[ttl_k]).strip() if (ttl_k and row[ttl_k]) else ""
        dt   = str(row[dt_k]).strip()  if (dt_k  and row[dt_k])  else ""
        iss  = str(row[iss_k]).strip() if (iss_k and row[iss_k]) else ""
        print(f"\n  레벨={lv!r}  섹션={sec!r}  호수={iss}  날짜={dt}")
        print(f"  제목: {ttl[:70]}")
        print(f"  본문: {txt[:200].replace(chr(10),' ')}{'...' if len(txt)>200 else ''}")
else:
    print("\n비정상 레벨 라벨 행: 없음")


# ══════════════════════════════════════════════════════════════════════════
# 2. KINDER/KIDS 분포 재추출 (KIDS L0 제외)
# ══════════════════════════════════════════════════════════════════════════
def analyze_sheet(sheet_name: str, level_prefix: str, exclude_l0: bool):
    rows, hdr, lv_col, tx_col, sc_col, ttl_col, *_ = load_sheet(sheet_name)

    total_rows = 0
    ex_l0 = 0
    ex_section = 0
    ex_classifier = 0
    ex_empty = 0
    data: dict[str, list] = {}   # key -> [(avg, title, fmt, txt)]

    for row in rows:
        if not row: continue
        lv  = str(row[lv_col]).strip()  if row[lv_col]  else ""
        txt = str(row[tx_col]).strip()  if row[tx_col]  else ""
        sec = str(row[sc_col]).strip()  if (sc_col is not None and row[sc_col]) else ""
        ttl = str(row[ttl_col]).strip() if (ttl_col is not None and row[ttl_col]) else ""
        if not lv or not txt: continue
        total_rows += 1

        m = re.search(r"\d+", lv)
        if not m: continue
        level_num = int(m.group())
        key = f"{level_prefix}_L{level_num}"

        # KIDS L0 전부 제외
        if exclude_l0 and level_num == 0:
            ex_l0 += 1
            continue

        wc = len(re.findall(r"[A-Za-z']+", txt))
        if wc < 5:
            ex_empty += 1
            continue
        if sec in EXCLUDE_SECTIONS:
            ex_section += 1
            continue

        cls = classify(txt, key)
        if cls.skip_cefr:
            ex_classifier += 1
            continue

        avg = avg_sent_len(txt)
        if avg < 1.0:
            ex_empty += 1
            continue

        data.setdefault(key, []).append((avg, ttl, cls.article_type.value, txt))

    total_ex = ex_l0 + ex_section + ex_classifier + ex_empty
    total_art = sum(len(v) for v in data.values())

    l0_note = f" + L0제외 {ex_l0}건" if exclude_l0 else ""
    print(f"\n{'='*70}")
    print(f"{sheet_name}  (총 {total_rows}행{l0_note}"
          f" + 섹션제외 {ex_section}건 + classifier제외 {ex_classifier}건"
          f" + 빈텍스트 {ex_empty}건 = 제외 {total_ex}건,  최종 ARTICLE {total_art}건)")
    print(f"{'='*70}")

    for key in sorted(data.keys()):
        items = data[key]
        avgs = sorted(x[0] for x in items)
        n = len(avgs)
        if n == 0: continue

        p5v  = pct(avgs, 5)
        p10v = pct(avgs, 10)
        p15v = pct(avgs, 15)
        p25v = pct(avgs, 25)
        p50v = pct(avgs, 50)

        print(f"\n── {key}  n={n} ──")
        print(f"  p5={p5v:.1f}  p10={p10v:.1f}  p15={p15v:.1f}  p25={p25v:.1f}  p50={p50v:.1f}")

        band = [(a, ttl, fmt, t) for a, ttl, fmt, t in items if p5v <= a <= p15v]
        if not band:
            band = [(a, ttl, fmt, t) for a, ttl, fmt, t in items if a <= p15v]
        band.sort(key=lambda x: x[0])
        step = max(1, len(band) // 5)
        picks = [band[i] for i in range(0, min(len(band), step * 5), step)][:5]

        print(f"  하위 분위(p5~p15) 샘플 {len(picks)}건:")
        for i, (avg, ttl, fmt, txt) in enumerate(picks, 1):
            preview = txt[:200].replace("\n", " ")
            print(f"\n  [{i}] avg={avg:.1f}  포맷={fmt}  제목={ttl[:60] or '(없음)'}")
            print(f"       {preview}{'...' if len(txt)>200 else ''}")

print("\n\n" + "=" * 70)
print("분포 재추출")
print("=" * 70)
analyze_sheet("KINDER", "KINDER", exclude_l0=False)   # KINDER는 점검 결과 나온 뒤 결정
analyze_sheet("KIDS",   "KIDS",   exclude_l0=True)    # KIDS L0 제외
