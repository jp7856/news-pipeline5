"""KINDER / KIDS avg_sentence_len 분포 및 하위 분위(p5~p15) 샘플.

필터 기준:
  1. EXCLUDE_SECTIONS (사진·단신·포맷 섹션)
  2. classify().skip_cefr == True 제외 (BRIEF·DIALOGUE 전부)
  3. 영단어 5개 미만 텍스트 제거 (거의 비어있는 행)
결과: 순수 ARTICLE만 남음.
"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl
from agents.sub_agents.article_classifier import classify

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"

# KINDER/KIDS 공통 제외 섹션 — "우리가 생성하지 않는 포맷"
EXCLUDE_SECTIONS = {
    "Photo News",                      # 사진 캡션
    "NE You",                          # 학생 투고
    "Cover",                           # 표지 단문
    "Did You Know", "Did You Know?",   # 퀴즈형 단신
    "Debating",                        # 대화체 토론 프롬프트
    "Q & A",                           # 인터뷰 Q&A 포맷
    "Cartoon",                         # 만화
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

def analyze_sheet(sheet_name: str, level_prefix: str):
    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(c).strip() if c else "" for c in rows[0]]

    lv_col  = next(i for i,h in enumerate(hdr) if "레벨"  in h or "level"   in h.lower())
    tx_col  = next(i for i,h in enumerate(hdr) if "본문"  in h or "text"    in h.lower())
    sc_col  = next((i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower()), None)
    ttl_col = next((i for i,h in enumerate(hdr) if "제목" in h or "title"   in h.lower()), None)

    total_rows = 0
    ex_section = 0
    ex_classifier = 0
    ex_empty = 0
    # key -> [(avg, title, article_type_str, txt)]
    data: dict[str, list] = {}

    for row in rows[1:]:
        if not row: continue
        lv  = str(row[lv_col]).strip()  if row[lv_col]  else ""
        txt = str(row[tx_col]).strip()  if row[tx_col]  else ""
        sec = str(row[sc_col]).strip()  if (sc_col is not None and row[sc_col]) else ""
        ttl = str(row[ttl_col]).strip() if (ttl_col is not None and row[ttl_col]) else ""
        if not lv or not txt: continue
        total_rows += 1

        m = re.search(r"\d+", lv)
        if not m: continue
        key = f"{level_prefix}_L{m.group()}"

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

    total_ex = ex_section + ex_classifier + ex_empty
    total_art = sum(len(v) for v in data.values())

    print(f"\n{'='*70}")
    print(f"{sheet_name}  (총 {total_rows}행 → 섹션제외 {ex_section}건 + classifier제외 {ex_classifier}건"
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

        # p5~p15 구간 기사 수집 후 균등 5개 샘플
        band = [(a, ttl, fmt, t) for a, ttl, fmt, t in items if p5v <= a <= p15v]
        if not band:
            # p15 미만으로 확대
            band = [(a, ttl, fmt, t) for a, ttl, fmt, t in items if a <= p15v]
        band.sort(key=lambda x: x[0])

        step = max(1, len(band) // 5)
        picks = [band[i] for i in range(0, min(len(band), step * 5), step)][:5]

        print(f"  하위 분위(p5~p15) 샘플 {len(picks)}건:")
        for i, (avg, ttl, fmt, txt) in enumerate(picks, 1):
            preview = txt[:200].replace("\n", " ")
            print(f"\n  [{i}] avg={avg:.1f}  포맷={fmt}  제목={ttl[:60] or '(없음)'}")
            print(f"       {preview}{'...' if len(txt)>200 else ''}")

analyze_sheet("KINDER", "KINDER")
analyze_sheet("KIDS",   "KIDS")
