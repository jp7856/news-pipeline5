"""Pros&Cons 토론형 기사 감사 + classifier 보강 검토 + 탈락률 재계산.

목표:
  1. 현재 ARTICLE 풀에 남아있는 Pros&Cons 형 토론 활동지 건수 파악 (매체·레벨별)
  2. 새 패턴으로 잡을 수 있는지 검토 (false positive 없이)
  3. 토론형 제외 후 avg_min 탈락률 재계산 → 이전 표와 비교
값 변경 없음 — 분석 전용.
"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl
from agents.sub_agents.cefr_checker import LEVELS
from agents.sub_agents.article_classifier import classify

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"

EXCLUDE_SECTIONS = {
    "Photo News","Briefs","Star Brief","News in Brief","Cartoon",
    "Did You Know","Did You Know?","Debating","Cover","Q & A","NE You",
    "My Journal","Book Review","Stories","Story",
    "Readings for Junior","VoA Broadcast News",
    "Think About It","My Diary",
}
SHEET_CFG = {
    "KINDER":   ("KINDER",   0),
    "KIDS":     ("KIDS",    50),
    "JUNIOR":   ("JUNIOR",  80),
    "JUNIOR M": ("JUNIORM",100),
    "TIMES":    ("TIMES",  100),
}
_SE = re.compile(r"(?<=[.!?])\s+")

def avg_sl(t: str) -> float:
    p = [len(re.findall(r"[A-Za-z']+", s)) for s in _SE.split(t.strip())]
    p = [w for w in p if w >= 1]
    return sum(p) / len(p) if p else 0.0

# ── 제안하는 Pros&Cons 탐지 패턴 ────────────────────────────────────────────
# (1) "Read the article ... on page N / on Page N" 오프너
_PC_OPENER = re.compile(
    r"Read the article\b.{0,120}[Pp]age\s*\d",
    re.IGNORECASE | re.DOTALL,
)
# (2) "Person A" / "Person B" 레이블 2개 이상
_PERSON_LBL = re.compile(r"(?<!\w)Person\s+[A-D](?!\w)")

def is_pros_cons(text: str) -> bool:
    if _PC_OPENER.search(text):
        return True
    labels = set(_PERSON_LBL.findall(text))
    return len(labels) >= 2


# ── 정상 뉴스 섹션(false positive 검사 기준) ───────────────────────────────
NORMAL_SECS = {
    "Nation","World","Global","Science","Sports","Culture","Lifestyle",
    "Key Issue","People","Science & Technology","Headlines News","Entertainment",
    "World Tour","Focus","Global",
}

ORDER = [
    "KINDER_L1","KINDER_L2",
    "KIDS_L1","KIDS_L2","KIDS_L3",
    "JUNIOR_L1","JUNIOR_L2","JUNIOR_L3",
    "JUNIORM_L1","JUNIORM_L2",
    "TIMES_L1","TIMES_L2","TIMES_L3",
]

# ── 수집 ────────────────────────────────────────────────────────────────────
# key → {n_article, n_pc_hit, n_pc_sec, failed_orig, failed_clean, fp_samples}
stats: dict[str, dict] = {}
# false positive 검사용
fp_normal: list[tuple] = []  # (key, sec, txt)

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)

for sheet_name, (prefix, min_wc) in SHEET_CFG.items():
    ws   = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    hdr  = [str(c).strip() if c else "" for c in rows[0]]
    lv_c = next((i for i,h in enumerate(hdr) if "레벨" in h or "level"   in h.lower()), None)
    tx_c = next((i for i,h in enumerate(hdr) if "본문" in h or "text"    in h.lower()), None)
    sc_c = next((i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower()), None)
    if lv_c is None or tx_c is None: continue

    for row in rows[1:]:
        if not row or len(row) <= max(lv_c, tx_c): continue
        lval = str(row[lv_c]).strip() if row[lv_c] else ""
        txt  = str(row[tx_c]).strip() if row[tx_c] else ""
        sec  = str(row[sc_c]).strip() if (sc_c and row[sc_c]) else ""
        if not lval or len(txt) < 50 or sec in EXCLUDE_SECTIONS: continue
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

        pc = is_pros_cons(txt)
        bucket = stats.setdefault(key, {
            "n_article": 0, "n_pc": 0, "pc_secs": {},
            "failed_orig": 0, "failed_clean": 0,
            "pc_samples": [],
        })
        bucket["n_article"] += 1
        if pc:
            bucket["n_pc"] += 1
            bucket["pc_secs"][sec] = bucket["pc_secs"].get(sec, 0) + 1
            if len(bucket["pc_samples"]) < 2:
                bucket["pc_samples"].append((sec, avg, txt[:300]))
        else:
            # false positive 검사: 정상 섹션인데 is_pros_cons True → 여기서는 False이므로 역방향 체크
            pass

        spec = LEVELS[key]
        if avg < spec.avg_min:
            bucket["failed_orig"] += 1
            if not pc:
                bucket["failed_clean"] += 1

        # false positive 검사: 정상 섹션에서 is_pros_cons 가 잡히면 fp
        if pc and sec in NORMAL_SECS:
            fp_normal.append((key, sec, avg, txt[:200]))


# ── 출력 1: Pros&Cons 건수 ────────────────────────────────────────────────
print("=" * 72)
print("1. ARTICLE 풀 내 Pros&Cons 형 토론 활동지 건수 (is_pros_cons() 기준)")
print("=" * 72)
print(f"{'레벨':<13}  {'ARTICLE':>8}  {'PC건수':>7}  {'PC%':>5}  섹션별")
print("─" * 72)
total_art = total_pc = 0
for key in ORDER:
    if key not in stats: continue
    b = stats[key]
    n  = b["n_article"]; pc = b["n_pc"]
    total_art += n; total_pc += pc
    pct = pc/n*100 if n else 0
    sec_str = "  ".join(f"{s}:{c}" for s,c in sorted(b["pc_secs"].items(), key=lambda x:-x[1]))
    if pc:
        print(f"{key:<13}  {n:>8}  {pc:>7}  {pct:>4.1f}%  {sec_str}")
    else:
        print(f"{key:<13}  {n:>8}  {pc:>7}  {pct:>4.1f}%")
print("─" * 72)
print(f"{'합계':<13}  {total_art:>8}  {total_pc:>7}  {total_pc/total_art*100:.1f}%")

# ── 출력 2: False positive 확인 ──────────────────────────────────────────
print()
print("=" * 72)
print("2. False positive 검사 — 정상 뉴스 섹션에서 is_pros_cons() 오판정")
print("=" * 72)
if not fp_normal:
    print("  → 정상 섹션 false positive: 0건")
else:
    print(f"  → 정상 섹션 false positive: {len(fp_normal)}건")
    for key, sec, avg, preview in fp_normal[:5]:
        print(f"\n  [{key}] 섹션={sec} avg={avg:.2f}")
        print(f"  {preview.replace(chr(10),' ')}...")

# ── 출력 3: 샘플 — PC 패턴 잡힌 기사 확인 ────────────────────────────────
print()
print("=" * 72)
print("3. PC 패턴 잡힌 기사 샘플 (레벨별 최대 1개씩, TIMES/JUNIOR 중심)")
print("=" * 72)
for key in ["TIMES_L1","TIMES_L2","TIMES_L3","JUNIOR_L1","JUNIOR_L2","JUNIOR_L3","JUNIORM_L1"]:
    if key not in stats or not stats[key]["pc_samples"]: continue
    sec, avg, preview = stats[key]["pc_samples"][0]
    print(f"\n[{key}] 섹션={sec} avg={avg:.2f}")
    print(f"  {preview.replace(chr(10),' ')}...")

# ── 출력 4: 탈락률 비교 ──────────────────────────────────────────────────
print()
print("=" * 72)
print("4. avg_min 탈락률 비교  (이전=PC포함 / 신규=PC제외 후)")
print("=" * 72)
print(f"{'레벨':<13} {'avg_min':>7}  {'이전탈락':>8} {'이전%':>6}  {'신규탈락':>8} {'신규%':>6}  {'차이':>6}")
print("─" * 72)
for key in ORDER:
    if key not in stats: continue
    b    = stats[key]
    spec = LEVELS[key]
    n    = b["n_article"]
    fo   = b["failed_orig"]
    fc   = b["failed_clean"]
    n_clean = n - b["n_pc"]
    pct_o = fo / n       * 100 if n       else 0
    pct_c = fc / n_clean * 100 if n_clean else 0
    diff  = pct_c - pct_o
    diff_str = f"{diff:+.1f}%" if diff else "  —"
    print(f"{key:<13} {spec.avg_min:>7}  {fo:>8} {pct_o:>5.1f}%  {fc:>8} {pct_c:>5.1f}%  {diff_str:>6}")
