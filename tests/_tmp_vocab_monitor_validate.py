"""
_tmp_vocab_monitor_validate.py — vocab_monitor 2단계 플래그 검증.

대상:
  - CCTV 767호 (TIMES_L2, 드리프트 기준 기사)
  - TIMES_L2 2024+ 고C2VA 기사 전체 (토픽 전문어 후보)

가설:
  CCTV → STRONG (C2VA 높음 + NOT 단어 출현)
  토픽 기사들 → WEAK  (C2VA 높지만 NOT 단어 없음)

Phase 1: TIMES_L2 전체 코퍼스 C2VA 분포 + 섹션별 baseline 계산
Phase 2: 대상 기사 check() 실행 — baseline은 여러 값(p75/p85/p90) 모두 보여줌
Phase 3: 요약 테이블

baseline 수치 미확정 — 결과 보고 사용자가 조정.
"""
import sys
import io
import re
import collections

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl

from agents.sub_agents.vocab_checker import NOT_WORDS
from agents.sub_agents.vocab_monitor import check, VocabFlag
from agents.sub_agents.article_classifier import classify

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"

EXCLUDE_SECTIONS = {
    "Photo News", "Briefs", "Star Brief", "News in Brief", "Cartoon",
    "Did You Know", "Did You Know?", "Debating", "Cover", "Q & A",
    "NE You", "My Journal", "Book Review", "Stories", "Story",
    "Readings for Junior", "VoA Broadcast News", "Think About It",
    "My Diary", "Debate",
}

_YR = re.compile(r"\b(20\d{2})\b")

SEP  = "=" * 72
SEP2 = "-" * 72


def pct_val(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(int(len(s) * p / 100), len(s) - 1)]


# ── 코퍼스 로딩 ───────────────────────────────────────────────────────────────
print("Loading corpus...", end="", flush=True)
wb  = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws  = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]

def ci(p):
    return next((i for i, h in enumerate(hdr) if p in h or p.lower() in h.lower()), None)

lv_col  = ci("레벨")
tx_col  = ci("본문")
sc_col  = ci("섹션")
dt_col  = ci("날짜")
iss_col = ci("호수")
ti_col  = ci("제목")  # 제목 컬럼 (없을 수 있음)

def gc(r, c):
    if c is None or len(r) <= c or r[c] is None:
        return ""
    return str(r[c]).strip()

print(" done.\n")


# ── Phase 1: 전체 코퍼스 C2VA 분포 계산 ──────────────────────────────────────
print("Phase 1: C2VA 분포 계산 (전체 TIMES_L2, 연도 무관) — 느릴 수 있음...")

# section → list of c2va_pct
section_c2va: dict[str, list[float]] = collections.defaultdict(list)
all_c2va: list[float] = []
total_arts = 0

for row in rows[1:]:
    if not row:
        continue
    if re.sub(r"[^0-9]", "", gc(row, lv_col)) != "2":
        continue
    sc = gc(row, sc_col)
    tx = gc(row, tx_col)
    if sc in EXCLUDE_SECTIONS or not tx or len(tx) < 30:
        continue
    cls = classify(tx, "TIMES_L2")
    if cls.skip_cefr:
        continue
    # baseline용: NOT 단어 없이 C2VA만 (체크 함수에서 baseline_pct=0으로 부르면
    # 모든 기사가 above_baseline이 됨 — pct 값만 필요)
    r = check(tx, baseline_pct=0.0)
    section_c2va[sc].append(r.c2va_pct)
    all_c2va.append(r.c2va_pct)
    total_arts += 1
    if total_arts % 100 == 0:
        print(f"  {total_arts}건 처리 중...", flush=True)

print(f"  완료: 총 {total_arts}건\n")

# 전체 분포
print(SEP)
print(f"전체 TIMES_L2 C2VA 분포 (n={total_arts})")
print(SEP)
for p in (50, 75, 85, 90, 95):
    v = pct_val(all_c2va, p)
    print(f"  p{p:2d} = {v:.2f}%")

# 섹션별 분포
print(f"\n섹션별 C2VA 분포 (n≥10인 섹션만)")
print(SEP2)
for sc in sorted(section_c2va, key=lambda s: -len(section_c2va[s])):
    vals = section_c2va[sc]
    if len(vals) < 10:
        continue
    p75 = pct_val(vals, 75)
    p85 = pct_val(vals, 85)
    p90 = pct_val(vals, 90)
    p95 = pct_val(vals, 95)
    print(f"  {sc:<30} n={len(vals):3d}  p75={p75:.2f}  p85={p85:.2f}  p90={p90:.2f}  p95={p95:.2f}")

p90_overall = pct_val(all_c2va, 90)
p85_overall = pct_val(all_c2va, 85)
p75_overall = pct_val(all_c2va, 75)


# ── Phase 2: 대상 기사 수집 ────────────────────────────────────────────────────
print(f"\n{SEP}")
print("Phase 2: 대상 기사 수집")
print(SEP)

# 2-1. CCTV 767호: iss="767" L2
cctv_articles = []
for row in rows[1:]:
    if not row:
        continue
    if re.sub(r"[^0-9]", "", gc(row, lv_col)) != "2":
        continue
    iss = gc(row, iss_col)
    if iss != "767":
        continue
    sc  = gc(row, sc_col)
    tx  = gc(row, tx_col)
    dt  = gc(row, dt_col)
    ti  = gc(row, ti_col) if ti_col is not None else ""
    if not tx or len(tx) < 30:
        continue
    cls = classify(tx, "TIMES_L2")
    if cls.skip_cefr:
        continue
    cctv_articles.append({"iss": iss, "sc": sc, "dt": dt, "ti": ti, "tx": tx})

print(f"\nCCTV 767호 후보 ({len(cctv_articles)}건): {[a['sc'] for a in cctv_articles]}")

# 2-2. 2024+ 고C2VA 기사 (재스캔)
TARGET_THRESHOLD = 4.0  # 이 이상인 기사를 토픽 테스트셋으로 수집
topic_articles = []
print(f"\n2024+ TIMES_L2 C2VA ≥ {TARGET_THRESHOLD}% 기사 수집 중...", end="", flush=True)

for row in rows[1:]:
    if not row:
        continue
    if re.sub(r"[^0-9]", "", gc(row, lv_col)) != "2":
        continue
    sc  = gc(row, sc_col)
    tx  = gc(row, tx_col)
    dt  = gc(row, dt_col)
    iss = gc(row, iss_col)
    ti  = gc(row, ti_col) if ti_col is not None else ""
    if sc in EXCLUDE_SECTIONS or not tx or len(tx) < 30:
        continue
    ym = _YR.search(dt)
    yr = int(ym.group()) if ym else None
    if yr is None or yr < 2024:
        continue
    cls = classify(tx, "TIMES_L2")
    if cls.skip_cefr:
        continue
    r = check(tx, baseline_pct=0.0)
    if r.c2va_pct >= TARGET_THRESHOLD:
        topic_articles.append({"iss": iss, "sc": sc, "dt": dt, "ti": ti, "tx": tx,
                                "c2va_pct": r.c2va_pct, "c2va_words": r.c2va_words})

print(f" {len(topic_articles)}건\n")


# ── Phase 3: 플래그 적용 — 여러 baseline 값 비교 ──────────────────────────────
def flag_symbol(flag: VocabFlag) -> str:
    return {"NONE": "    NONE", "WEAK": "    WEAK", "STRONG": "★ STRONG"}[flag.value]

def run_for_article(art: dict, baselines: dict[str, float]) -> dict:
    results = {}
    for label, bline in baselines.items():
        r = check(art["tx"], baseline_pct=bline)
        results[label] = r
    return results


BASELINES = {
    f"p75({p75_overall:.2f}%)": p75_overall,
    f"p85({p85_overall:.2f}%)": p85_overall,
    f"p90({p90_overall:.2f}%)": p90_overall,
}

print(SEP)
print("Phase 3: 플래그 결과")
print(SEP)
print(f"NOT 단어 목록 ({len(NOT_WORDS)}개): {', '.join(NOT_WORDS)}\n")

# ── CCTV 767호 ─────────────────────────────────────────────────────────────────
print("[ CCTV 767호 ]")
print(SEP2)

if not cctv_articles:
    print("  !! 767호 L2 기사를 찾지 못했음.")
else:
    for art in cctv_articles:
        r_full = check(art["tx"], baseline_pct=0.0)
        print(f"  섹션: {art['sc']}  |  날짜: {art['dt']}")
        print(f"  제목: {art['ti'][:70]}" if art["ti"] else f"  본문앞: {art['tx'][:80]}")
        print(f"  C2VA: {r_full.c2va_pct:.2f}% ({r_full.c2va_count}/{r_full.total_words})")
        print(f"  C2동사·부사: {', '.join(r_full.c2va_words)}")
        print(f"  NOT 단어 출현: {r_full.not_word_hits if r_full.not_word_hits else '없음'}")
        print()
        for label, bline in BASELINES.items():
            r = check(art["tx"], baseline_pct=bline)
            print(f"    baseline={label:20s}  →  {flag_symbol(r.flag)}  |  {r.flag_reason}")
        print()

# ── 토픽 기사들 ────────────────────────────────────────────────────────────────
print(f"\n[ 2024+ 고C2VA 기사  ({len(topic_articles)}건) ]")
print(SEP2)

topic_articles_sorted = sorted(topic_articles, key=lambda a: -a["c2va_pct"])

for art in topic_articles_sorted:
    r_full = check(art["tx"], baseline_pct=0.0)
    label_str = f"{art['iss']} [{art['sc']}] {art['dt']}"
    print(f"  {label_str}")
    print(f"  제목: {art['ti'][:70]}" if art["ti"] else f"  본문앞: {art['tx'][:80]}")
    print(f"  C2VA: {r_full.c2va_pct:.2f}%  C2동사·부사: {', '.join(r_full.c2va_words)}")
    print(f"  NOT 단어: {r_full.not_word_hits if r_full.not_word_hits else '없음'}")
    for label, bline in BASELINES.items():
        r = check(art["tx"], baseline_pct=bline)
        print(f"    {label:20s}  →  {flag_symbol(r.flag)}")
    print()


# ── Phase 4: 요약 테이블 ──────────────────────────────────────────────────────
print(SEP)
print("Phase 4: 요약 — baseline별 STRONG/WEAK/NONE 분류")
print(SEP)

all_test = [{"label": f"CCTV 767호 [{a['sc']}]", **a} for a in cctv_articles] \
         + [{"label": f"{a['iss']} [{a['sc']}]", **a} for a in topic_articles_sorted]

for label, bline in BASELINES.items():
    counts = collections.Counter()
    strong_arts = []
    weak_arts   = []
    for art in all_test:
        r = check(art["tx"], baseline_pct=bline)
        counts[r.flag.value] += 1
        if r.flag == VocabFlag.STRONG:
            strong_arts.append(art["label"])
        elif r.flag == VocabFlag.WEAK:
            weak_arts.append(art["label"])

    total = len(all_test)
    print(f"\nbaseline = {label}")
    print(f"  STRONG: {counts['STRONG']:2d}/{total}  WEAK: {counts['WEAK']:2d}/{total}  NONE: {counts['NONE']:2d}/{total}")
    if strong_arts:
        print(f"  STRONG 목록: {', '.join(strong_arts[:5])}")
    if weak_arts:
        print(f"  WEAK 목록  : {', '.join(weak_arts[:8])}")
