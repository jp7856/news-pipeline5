"""13개 전체 레벨 avg_sentence_len 분포 한 표 — BRIEF/DIALOGUE 제외 후."""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

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
    "Think About It",                  # KINDER 토론/의견나열 포맷
    "My Diary",                        # KINDER 1인칭 일기체
    # Speak Out: 섹션 단위 제외 금지 — classifier DIALOGUE 판정만 제외
}

# 시트명 → (레벨 표기 접두사, MIN_WC)
SHEET_CFG: dict[str, tuple[str, int]] = {
    "KINDER":   ("KINDER",  0),
    "KIDS":     ("KIDS",   50),
    "JUNIOR":   ("JUNIOR", 80),
    "JUNIOR M": ("JUNIORM",100),
    "TIMES":    ("TIMES",  100),
}

def pct(xs: list[float], p: int) -> float:
    s = sorted(xs)
    return s[min(int(len(s) * p / 100), len(s) - 1)]

# ── 데이터 수집 ────────────────────────────────────────────────────────────
avgs: dict[str, list[float]] = {}   # cefr_key → avg 리스트

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)

for sheet_name, (prefix, min_wc) in SHEET_CFG.items():
    ws   = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    hdr  = [str(c).strip() if c else "" for c in rows[0]]
    lv_col  = next((i for i,h in enumerate(hdr) if "레벨" in h or "level"   in h.lower()), None)
    tx_col  = next((i for i,h in enumerate(hdr) if "본문" in h or "text"    in h.lower()), None)
    sc_col  = next((i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower()), None)
    if lv_col is None or tx_col is None:
        continue

    for row in rows[1:]:
        if not row or len(row) <= max(lv_col, tx_col):
            continue
        lv  = str(row[lv_col]).strip() if row[lv_col]  else ""
        txt = str(row[tx_col]).strip() if row[tx_col]  else ""
        sec = str(row[sc_col]).strip() if (sc_col and row[sc_col]) else ""

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
            continue                                      # KIDS L0 = 2010~2012 아카이브, 현행 아님
        key = f"{prefix}_L{m.group()}"
        if key not in LEVELS:
            continue

        if classify(txt, key).skip_cefr:
            continue

        avg = validate(txt, key).avg_sentence_len
        avgs.setdefault(key, []).append(avg)

# ── 난이도 오름차순 정렬 ──────────────────────────────────────────────────
ORDER = [
    "KINDER_L1", "KINDER_L2",
    "KIDS_L1",   "KIDS_L2",   "KIDS_L3",
    "JUNIOR_L1", "JUNIOR_L2", "JUNIOR_L3",
    "JUNIORM_L1","JUNIORM_L2",
    "TIMES_L1",  "TIMES_L2",  "TIMES_L3",
]

# ── 출력 ──────────────────────────────────────────────────────────────────
HDR  = f"{'레벨':<13} {'n':>5}  {'avg_min':>7}  {'p10':>6} {'p25':>6} {'p50':>6} {'p75':>6}  {'판정'}"
SEP  = "─" * 72
print(HDR)
print(SEP)

prev_p50 = None
for key in ORDER:
    if key not in avgs:
        print(f"{key:<13}  {'—':>5}  (데이터 없음)")
        continue
    xs      = avgs[key]
    spec    = LEVELS[key]
    n       = len(xs)
    p10_v   = pct(xs, 10)
    p25_v   = pct(xs, 25)
    p50_v   = pct(xs, 50)
    p75_v   = pct(xs, 75)
    cur_min = spec.avg_min

    # avg_min이 p25 이상이면 "엄격", p10 이하면 "느슨"
    if cur_min >= p25_v:
        judge = "엄격(avg_min≥p25)"
    elif cur_min <= p10_v:
        judge = "느슨(avg_min≤p10)"
    else:
        judge = "적정"

    # 갭/겹침 표시
    gap_mark = ""
    if prev_p50 is not None:
        if p50_v < prev_p50 - 0.5:
            gap_mark = " ← 역전"
        elif p50_v < prev_p50 + 1.0:
            gap_mark = " ← 겹침"

    print(f"{key:<13} {n:>5}  {cur_min:>7.1f}  "
          f"{p10_v:>6.1f} {p25_v:>6.1f} {p50_v:>6.1f} {p75_v:>6.1f}  "
          f"{judge}{gap_mark}")
    prev_p50 = p50_v

print(SEP)
print("판정 기준: avg_min≥p25 → 엄격 / avg_min≤p10 → 느슨 / 그 사이 → 적정")
print("갭/겹침: 직전 레벨 p50 대비 이번 레벨 p50이 +1 미만이면 겹침, 역전이면 역전 표시")
