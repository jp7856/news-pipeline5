"""articles.xlsx — 단신·비산문 섹션 제외 + 100단어 미만 단신 필터 후 validate() 통과율. API 없음."""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import openpyxl
from agents.sub_agents.cefr_checker import validate, LEVELS
from agents.sub_agents.article_classifier import classify

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"
PREFIX = {"KINDER":"KINDER","KIDS":"KIDS","JUNIOR":"JUNIOR","TIMES":"TIMES","JUNIOR M":"JUNIORM"}

# ── 제외 섹션 (단신·사진기사·만화·비산문) ─────────────────────────────
EXCLUDE_SECTIONS = {
    "Photo News",                      # 전 매체 — 사진 캡션
    "Briefs", "Star Brief",            # TIMES 단신
    "News in Brief",                   # TIMES 단신
    "Cartoon",                         # TIMES 만화
    "Did You Know", "Did You Know?",   # JUNIOR 퀴즈형 단신
    "Debating",                        # KIDS 토론 프롬프트(avg 48wc)
    "Cover",                           # KIDS avg 45wc
    "Q & A",                           # TIMES 인터뷰 Q&A 포맷(avg 83wc)
    "NE You",                          # 학생 투고 공간 — 파이프라인 생성 대상 아님
    "My Journal", "Book Review",       # TIMES 독자 기고·서평 — 파이프라인 생성 대상 아님
    "Stories", "Story",                # TIMES 창작소설 — 파이프라인 생성 대상 아님
    "Readings for Junior",             # TIMES 보충읽기 — 파이프라인 생성 대상 아님
    "VoA Broadcast News",              # TIMES L3 방송 스크립트 — 파이프라인 생성 대상 아님
    "Think About It",                  # KINDER 토론/의견나열 포맷 — 파이프라인 생성 대상 아님
    "My Diary",                        # KINDER 1인칭 일기체 — 파이프라인 생성 대상 아님
    "Debate",                          # JUNIOR L3 토론 에세이 — avg_p50=9.7, 게이트 대상 아님
    # Speak Out: 섹션 단위 제외 금지 — classifier DIALOGUE 판정만 제외
}

# 레벨별 단어 수 하한 — 섹션 필터에서 빠진 단신 제거
# KINDER는 기사 자체가 짧으므로 필터 없음(0); 나머지는 정규 기사 최솟값 기준
MIN_WC_BY_SHEET: dict[str, int] = {
    "KINDER":   0,    # 기사 자체가 40~90단어 — 단신 구분 불가
    "KIDS":    50,    # L1 최솟값 60단어 기준으로 여유
    "JUNIOR":  80,    # L1 최솟값 115단어 기준으로 여유
    "JUNIOR M":100,   # L1 최솟값 150단어 기준으로 여유
    "TIMES":   100,   # L1 최솟값 110단어 기준으로 여유
}

def pct(xs, p):
    s = sorted(xs)
    return s[min(int(len(s)*p/100), len(s)-1)]

_YEAR_RE  = re.compile(r'\b(20\d{2})\b')
YEAR_CUTOFF = 2024

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)

all_buckets: dict[str, list] = {}
skip_counts: dict[str, dict[str, int]] = {}   # key → {BRIEF: n, DIALOGUE: n}

for sheet_name in ["KINDER", "KIDS", "JUNIOR", "TIMES", "JUNIOR M"]:
    ws   = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    hdr  = [str(c).strip() if c else "" for c in rows[0]]
    lv_col  = next((i for i,h in enumerate(hdr) if "레벨" in h or "level" in h.lower()), None)
    tx_col  = next((i for i,h in enumerate(hdr) if "본문" in h or "text" in h.lower()), None)
    sec_col = next((i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower()), None)
    dt_col  = next((i for i,h in enumerate(hdr) if "날짜" in h or "date"    in h.lower()), None)
    if lv_col is None or tx_col is None: continue

    for row in rows[1:]:
        if not row or len(row) <= max(lv_col, tx_col): continue
        lv  = str(row[lv_col]).strip()  if row[lv_col]  else ""
        txt = str(row[tx_col]).strip()  if row[tx_col]  else ""
        sec = str(row[sec_col]).strip() if (sec_col and row[sec_col]) else ""
        if not lv or len(txt) < 50: continue
        if sec in EXCLUDE_SECTIONS: continue          # 섹션 단위 단신 제외
        wc = len(re.findall(r"[A-Za-z']+", txt))
        if wc < MIN_WC_BY_SHEET.get(sheet_name, 0): continue  # 레벨별 단신 필터
        num = re.search(r"\d+", lv)
        if not num: continue
        if int(num.group()) == 0: continue                # KIDS L0 = 2010~2012 아카이브, 현행 아님
        yr = None
        if dt_col is not None and len(row) > dt_col and row[dt_col]:
            ym = _YEAR_RE.search(str(row[dt_col]))
            if ym: yr = int(ym.group())
        if yr is not None and yr < YEAR_CUTOFF:
            continue                                       # 아카이브 제외 (2024~ 현행 기준)
        key = f"{PREFIX[sheet_name]}_L{num.group()}"
        if key not in LEVELS: continue
        art_cls = classify(txt, key)
        if art_cls.skip_cefr:
            bucket = skip_counts.setdefault(key, {})
            bucket[art_cls.article_type.value] = bucket.get(art_cls.article_type.value, 0) + 1
            continue
        all_buckets.setdefault(key, []).append(validate(txt, key))

# ── 결과 출력 ─────────────────────────────────────────────────────────
print(f"{'레벨키':<14} {'n':>5}  {'통과율':>6}  "
      f"{'too_easy':>8} {'FK↑':>4}  "
      f"{'avg p50':>7} {'avg p90':>7}  "
      f"{'avg_min':>7} {'fk_max':>6}")
print("=" * 82)

for key in sorted(all_buckets):
    results  = all_buckets[key]
    n        = len(results)
    passed   = sum(1 for r in results if r.passed)
    too_easy = sum(1 for r in results if r.too_easy)
    fk_over  = sum(1 for r in results
                   if any("FK" in v and "참고" not in v for v in r.violations))
    avgs     = [r.avg_sentence_len for r in results]
    spec     = LEVELS[key]
    print(f"{key:<14} {n:>5}  {passed/n*100:>5.0f}%  "
          f"{too_easy:>7}건 {fk_over:>3}건  "
          f"{pct(avgs,50):>7.1f} {pct(avgs,90):>7.1f}  "
          f"{spec.avg_min:>7.1f} {spec.fk_max:>6.1f}")

print("=" * 82)

# ── avg_min 재보정 제안 ────────────────────────────────────────────────
print()
print(f"{'레벨키':<14}  {'avg p10':>7}  {'avg_min 현행':>11}  {'제안(p10 반올림)':>14}  {'변경 여부':>8}")
print("─" * 65)
for key in sorted(all_buckets):
    avgs = [r.avg_sentence_len for r in all_buckets[key]]
    p10  = pct(avgs, 10)
    cur  = LEVELS[key].avg_min
    new  = max(1.0, round(p10 * 2) / 2)
    flag = f"{cur:.1f} → {new:.1f}" if abs(cur - new) >= 0.5 else "—"
    print(f"{key:<14}  {p10:>7.1f}  {cur:>11.1f}  {new:>14.1f}  {flag:>10}")

# ── 분류기 제외 건수 ──────────────────────────────────────────────────────
if skip_counts:
    print()
    print(f"{'레벨키':<14}  {'BRIEF':>6}  {'DIALOGUE':>9}  {'소계':>6}")
    print("─" * 42)
    for key in sorted(skip_counts):
        b = skip_counts[key].get("BRIEF", 0)
        d = skip_counts[key].get("DIALOGUE", 0)
        print(f"{key:<14}  {b:>6}건  {d:>8}건  {b+d:>5}건")
