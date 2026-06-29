"""avg_min 탈락률 재계산 — 2024 이전 행 제외.

두 풀을 한 번에 계산해 나란히 비교:
  OLD: 연도 필터 없음 (이전 결과)
  NEW: year >= 2024 만 포함
게이트 값 변경 없음.
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
    "Readings for Junior","VoA Broadcast News","Think About It","My Diary",
}
SHEET_CFG = {
    "KINDER":   ("KINDER",   0),
    "KIDS":     ("KIDS",    50),
    "JUNIOR":   ("JUNIOR",  80),
    "JUNIOR M": ("JUNIORM",100),
    "TIMES":    ("TIMES",  100),
}
ORDER = [
    "KINDER_L1","KINDER_L2",
    "KIDS_L1","KIDS_L2","KIDS_L3",
    "JUNIOR_L1","JUNIOR_L2","JUNIOR_L3",
    "JUNIORM_L1","JUNIORM_L2",
    "TIMES_L1","TIMES_L2","TIMES_L3",
]
_SE      = re.compile(r"(?<=[.!?])\s+")
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
YEAR_CUTOFF = 2024   # 이 연도 이상만 포함

def avg_sl(t: str) -> float:
    p = [len(re.findall(r"[A-Za-z']+", s)) for s in _SE.split(t.strip())]
    p = [w for w in p if w >= 1]
    return sum(p) / len(p) if p else 0.0

# key → {old: {n,fail}, new: {n,fail}}
stats: dict[str, dict] = {}

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)

for sheet_name, (prefix, min_wc) in SHEET_CFG.items():
    ws   = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    hdr  = [str(c).strip() if c else "" for c in rows[0]]
    lv_c  = next((i for i,h in enumerate(hdr) if "레벨"  in h or "level"   in h.lower()), None)
    tx_c  = next((i for i,h in enumerate(hdr) if "본문"  in h or "text"    in h.lower()), None)
    sc_c  = next((i for i,h in enumerate(hdr) if "섹션"  in h or "section" in h.lower()), None)
    dt_c  = next((i for i,h in enumerate(hdr) if "날짜"  in h or "date"    in h.lower()), None)
    if lv_c is None or tx_c is None: continue

    for row in rows[1:]:
        if not row or len(row) <= max(lv_c, tx_c): continue
        lval = str(row[lv_c]).strip() if row[lv_c] else ""
        txt  = str(row[tx_c]).strip() if row[tx_c] else ""
        sec  = str(row[sc_c]).strip() if (sc_c  and row[sc_c]) else ""
        if not lval or len(txt) < 50 or sec in EXCL: continue
        wc = len(re.findall(r"[A-Za-z']+", txt))
        if wc < min_wc: continue
        m = re.search(r"\d+", lval)
        if not m or int(m.group()) == 0: continue
        key = f"{prefix}_L{m.group()}"
        if key not in LEVELS: continue
        cls = classify(txt, key)
        if cls.skip_cefr: continue
        avg = avg_sl(txt)
        if avg < 1.0: continue

        # 연도 파싱
        yr = None
        if dt_c is not None and len(row) > dt_c and row[dt_c]:
            ym = _YEAR_RE.search(str(row[dt_c]))
            if ym: yr = int(ym.group())

        failed = avg < LEVELS[key].avg_min
        b = stats.setdefault(key, {
            "old_n":0,"old_fail":0,
            "new_n":0,"new_fail":0,
        })
        # OLD: 전체 (연도 무관)
        b["old_n"] += 1
        if failed: b["old_fail"] += 1
        # NEW: year >= YEAR_CUTOFF (또는 날짜 없으면 포함)
        if yr is None or yr >= YEAR_CUTOFF:
            b["new_n"] += 1
            if failed: b["new_fail"] += 1

# ── 출력 ────────────────────────────────────────────────────────────────────
print(f"{'레벨':<13} {'avg_min':>7} │"
      f" {'OLD n':>7} {'OLD탈락':>7} {'OLD%':>6} │"
      f" {'NEW n':>7} {'NEW탈락':>7} {'NEW%':>6} │ {'변화':>6}")
print("─"*80)

for key in ORDER:
    if key not in stats:
        print(f"{key:<13} {'':>7} │ (데이터 없음)")
        continue
    b    = stats[key]
    spec = LEVELS[key]
    on = b["old_n"];  of = b["old_fail"]
    nn = b["new_n"];  nf = b["new_fail"]
    op = of/on*100 if on else 0
    np_ = nf/nn*100 if nn else 0
    diff = np_ - op
    diff_s = f"{diff:+.1f}%" if abs(diff) >= 0.05 else "  —"
    print(f"{key:<13} {spec.avg_min:>7} │"
          f" {on:>7} {of:>7} {op:>5.1f}% │"
          f" {nn:>7} {nf:>7} {np_:>5.1f}% │ {diff_s:>6}")

print()
print(f"NEW 기준: year >= {YEAR_CUTOFF} (날짜 없는 행 포함)")
print(f"제외 규칙: KIDS L0(level=0) + 확정 EXCLUDE_SECTIONS + year < {YEAR_CUTOFF}")
