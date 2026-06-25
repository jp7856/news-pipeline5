"""KIDS / JUNIOR / JUNIOR M 레벨 연속성 확인 — p25/p50/p75 한 표."""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import openpyxl
from agents.sub_agents.cefr_checker import validate, LEVELS
from agents.sub_agents.article_classifier import classify

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"
EXCLUDE_SECTIONS = {
    "Photo News", "Briefs", "Star Brief", "News in Brief",
    "Cartoon", "Did You Know", "Did You Know?", "Debating", "Cover", "Q & A",
    "NE You",
    "My Journal", "Book Review",       # TIMES 독자 기고·서평
    "Stories", "Story",                # TIMES 창작소설
    "Readings for Junior",             # TIMES 보충읽기
    "VoA Broadcast News",              # TIMES L3 방송 스크립트
}
MIN_WC_BY_SHEET = {
    "KINDER": 0, "KIDS": 50, "JUNIOR": 80, "JUNIOR M": 100,
}
PREFIX = {"KIDS": "KIDS", "JUNIOR": "JUNIOR", "JUNIOR M": "JUNIORM"}

def pct(xs, p):
    s = sorted(xs)
    return s[min(int(len(s) * p / 100), len(s) - 1)]

avgs: dict[str, list[float]] = {}
skip: dict[str, dict[str, int]] = {}

for sheet_name in ["KIDS", "JUNIOR", "JUNIOR M"]:
    wb  = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
    ws  = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    hdr  = [str(c).strip() if c else "" for c in rows[0]]
    lv_col  = next((i for i,h in enumerate(hdr) if "레벨" in h or "level" in h.lower()), None)
    tx_col  = next((i for i,h in enumerate(hdr) if "본문" in h or "text" in h.lower()), None)
    sc_col  = next((i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower()), None)
    if lv_col is None or tx_col is None: continue

    for row in rows[1:]:
        if not row or len(row) <= max(lv_col, tx_col): continue
        lv  = str(row[lv_col]).strip() if row[lv_col] else ""
        txt = str(row[tx_col]).strip() if row[tx_col] else ""
        sec = str(row[sc_col]).strip() if (sc_col and row[sc_col]) else ""
        if not lv or len(txt) < 30: continue
        if sec in EXCLUDE_SECTIONS: continue
        wc = len(re.findall(r"[A-Za-z']+", txt))
        if wc < MIN_WC_BY_SHEET.get(sheet_name, 0): continue
        num = re.search(r"\d+", lv)
        if not num: continue
        key = f"{PREFIX[sheet_name]}_L{num.group()}"
        if key not in LEVELS: continue

        cls = classify(txt, key)
        if cls.skip_cefr:
            bucket = skip.setdefault(key, {})
            bucket[cls.article_type.value] = bucket.get(cls.article_type.value, 0) + 1
            continue

        avgs.setdefault(key, []).append(validate(txt, key).avg_sentence_len)

# ── 출력 ──────────────────────────────────────────────────────────────────
ORDER = [
    "KIDS_L1", "KIDS_L2", "KIDS_L3",
    "JUNIOR_L1", "JUNIOR_L2", "JUNIOR_L3",
    "JUNIORM_L1", "JUNIORM_L2",
]

print(f"{'레벨키':<13} {'n':>5}  {'p25':>6} {'p50':>6} {'p75':>6}   "
      f"{'avg_min':>7} {'[현행]':>6}   {'skip':>5}")
print("─" * 68)

prev_p75 = None
for key in ORDER:
    xs   = avgs.get(key, [])
    spec = LEVELS[key]
    n    = len(xs)
    if n == 0:
        print(f"{key:<13}  {'—':>5}")
        continue

    p25 = pct(xs, 25)
    p50 = pct(xs, 50)
    p75 = pct(xs, 75)
    sk  = sum(skip.get(key, {}).values())

    # 이전 레벨 p75와의 관계 표시
    gap_note = ""
    if prev_p75 is not None:
        if p25 > prev_p75:
            gap_note = f"  ↑ GAP (+{p25-prev_p75:.1f})"
        elif p25 < prev_p75 - 1.0:
            gap_note = f"  ↔ OVERLAP (-{prev_p75-p25:.1f})"
        else:
            gap_note = "  ~ 연속"

    # 레벨 그룹 구분선
    if key in ("JUNIOR_L1", "JUNIORM_L1"):
        print()

    print(f"{key:<13} {n:>5}  {p25:>6.1f} {p50:>6.1f} {p75:>6.1f}   "
          f"{spec.avg_min:>7.1f} {'←' if spec.avg_min > p25 else ' ':>6}   "
          f"{sk:>5}건{gap_note}")
    prev_p75 = p75

print()
print("※ gap_note: GAP = 앞 레벨 p75 < 이 레벨 p25 (빈 구간 존재)")
print("            OVERLAP = 앞 레벨 p75 > 이 레벨 p25 (분포 겹침)")
print("            ~ 연속 = 거의 이어짐 (차이 1.0 이내)")
print("※ ← : avg_min이 p25보다 높음 → 실제 분포의 하위 25%+ 거부 중")
