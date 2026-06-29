"""avg_min 탈락 샘플 상세.

TIMES_L1/L2/L3, JUNIOR_L3, JUNIORM_L1 에서 avg_min 게이트 탈락 기사 8개씩.
TIMES_L1은 avg값 낮은순/중간/높은순으로 고르게 분포.
출력: 제목 / 섹션 / classifier 판정 / wc / avg / 본문 앞 250자.
"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl
from agents.sub_agents.cefr_checker import LEVELS
from agents.sub_agents.article_classifier import classify

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"

EXCLUDE_SECTIONS = {
    "Photo News", "Briefs", "Star Brief", "News in Brief",
    "Cartoon", "Did You Know", "Did You Know?",
    "Debating", "Cover", "Q & A",
    "NE You",
    "My Journal", "Book Review",
    "Stories", "Story",
    "Readings for Junior",
    "VoA Broadcast News",
    "Think About It",
    "My Diary",
}

SHEET_CFG = {
    "KINDER":   ("KINDER",   0),
    "KIDS":     ("KIDS",    50),
    "JUNIOR":   ("JUNIOR",  80),
    "JUNIOR M": ("JUNIORM", 100),
    "TIMES":    ("TIMES",   100),
}

TARGET_KEYS = {"TIMES_L1", "TIMES_L2", "TIMES_L3", "JUNIOR_L3", "JUNIORM_L1"}

_SENT_END = re.compile(r'(?<=[.!?])\s+')

def avg_sent_len(text: str) -> float:
    parts = _SENT_END.split(text.strip())
    wcs   = [len(re.findall(r"[A-Za-z']+", p)) for p in parts]
    wcs   = [w for w in wcs if w >= 1]
    return sum(wcs) / len(wcs) if wcs else 0.0

# key → [(ttl, sec, fmt, wc, avg, txt)]
pool: dict[str, list] = {}

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)

for sheet_name, (prefix, min_wc) in SHEET_CFG.items():
    ws   = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    hdr  = [str(c).strip() if c else "" for c in rows[0]]
    lv_col  = next((i for i,h in enumerate(hdr) if "레벨"  in h or "level"   in h.lower()), None)
    tx_col  = next((i for i,h in enumerate(hdr) if "본문"  in h or "text"    in h.lower()), None)
    sc_col  = next((i for i,h in enumerate(hdr) if "섹션"  in h or "section" in h.lower()), None)
    ttl_col = next((i for i,h in enumerate(hdr) if "제목"  in h or "title"   in h.lower()), None)
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
        if not m or int(m.group()) == 0:
            continue
        key = f"{prefix}_L{m.group()}"
        if key not in TARGET_KEYS:
            continue
        if key not in LEVELS:
            continue
        cls = classify(txt, key)
        if cls.skip_cefr:
            continue
        avg = avg_sent_len(txt)
        if avg < 1.0:
            continue
        if avg < LEVELS[key].avg_min:
            pool.setdefault(key, []).append(
                (ttl, sec, cls.article_type.value, wc, avg, txt)
            )

# ── 출력 ────────────────────────────────────────────────────────────────────
ORDER = ["TIMES_L1", "TIMES_L2", "TIMES_L3", "JUNIOR_L3", "JUNIORM_L1"]

def pick_spread(items, n=8):
    """avg 오름차순 정렬 후 인덱스를 n등분하여 고르게 추출."""
    s = sorted(items, key=lambda x: x[4])
    if len(s) <= n:
        return s
    step = (len(s) - 1) / (n - 1)
    return [s[round(step * i)] for i in range(n)]

def pick_uniform(items, n=8):
    """avg 오름차순 정렬 후 균등 추출 (고르게, 중복 없음)."""
    s = sorted(items, key=lambda x: x[4])
    if len(s) <= n:
        return s
    step = len(s) / n
    return [s[int(step * i + step / 2)] for i in range(n)]

for key in ORDER:
    entries = pool.get(key, [])
    spec    = LEVELS[key]
    n_total = len(entries)

    if key == "TIMES_L1":
        # 낮은/중간/높은 순으로 고르게
        picks = pick_spread(entries, 8)
        note  = "avg 낮은순→중간→높은순 고르게"
    else:
        picks = pick_uniform(entries, 8)
        note  = "avg 균등 추출"

    print("=" * 72)
    print(f"{key}  (avg_min={spec.avg_min}, 탈락 {n_total}건 → 샘플 {len(picks)}개, {note})")
    print("=" * 72)

    for i, (ttl, sec, fmt, wc, avg, txt) in enumerate(picks, 1):
        preview = txt[:250].replace("\n", " ")
        ttl_disp = ttl[:60] if ttl and ttl != "NE Times 전체메뉴" else "(제목없음)"
        print(f"\n[{i}]")
        print(f"  제목    : {ttl_disp}")
        print(f"  섹션    : {sec or '(없음)'}")
        print(f"  classifier: {fmt}  wc={wc}  avg={avg:.3f}")
        print(f"  본문    : {preview}{'...' if len(txt)>250 else ''}")

    print()
