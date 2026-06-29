"""TIMES_L2 현행 ARTICLE 풀 C1+ 어휘 비율 분포 확인."""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl
from agents.sub_agents.vocab_checker import measure, NOT_WORDS
from agents.sub_agents.article_classifier import classify

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"
YEAR_CUTOFF = 2024
_YEAR_RE = re.compile(r'\b(20\d{2})\b')

EXCLUDE_SECTIONS = {
    "Photo News", "Briefs", "Star Brief", "News in Brief",
    "Cartoon", "Did You Know", "Did You Know?",
    "Debating", "Cover", "Q & A",
    "NE You", "My Journal", "Book Review",
    "Stories", "Story", "Readings for Junior",
    "VoA Broadcast News", "Think About It", "My Diary", "Debate",
}

def pct(xs, p):
    if not xs:
        return 0.0
    s = sorted(xs)
    return s[min(int(len(s) * p / 100), len(s) - 1)]

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr = [str(c).strip() if c else "" for c in rows[0]]

lv_col  = next((i for i,h in enumerate(hdr) if "레벨" in h or "level"   in h.lower()), None)
tx_col  = next((i for i,h in enumerate(hdr) if "본문" in h or "text"    in h.lower()), None)
sc_col  = next((i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower()), None)
ttl_col = next((i for i,h in enumerate(hdr) if "제목" in h or "title"   in h.lower()), None)
dt_col  = next((i for i,h in enumerate(hdr) if "날짜" in h or "date"    in h.lower()), None)

if lv_col is None or tx_col is None:
    print(f"컬럼 감지 실패 — 헤더: {hdr}")
    sys.exit(1)

# (c1plus_pct, not_hits, title, total_words, c1, c2)
results: list[tuple] = []
skip = {"EXCLUDE_SEC": 0, "YEAR": 0, "BRIEF": 0, "DIALOGUE": 0}
total_l2 = 0

print("분석 중...", end="", flush=True)

for row in rows[1:]:
    if not row:
        continue
    needed = [c for c in [lv_col, tx_col, sc_col, dt_col, ttl_col] if c is not None]
    if needed and len(row) <= max(needed):
        continue

    lv_raw = str(row[lv_col]).strip() if row[lv_col] else ""
    # "LEVEL 2" / "L2" / "2" 등 모든 형태를 2로 정규화
    lv_norm = re.sub(r'[^0-9]', '', lv_raw)
    if lv_norm != "2":
        continue
    total_l2 += 1

    sc  = str(row[sc_col]).strip()  if sc_col  is not None and row[sc_col]  else ""
    tx  = str(row[tx_col]).strip()  if row[tx_col]  else ""
    ttl = str(row[ttl_col]).strip() if ttl_col is not None and row[ttl_col] else ""

    if sc in EXCLUDE_SECTIONS:
        skip["EXCLUDE_SEC"] += 1
        continue

    yr = None
    if dt_col is not None and len(row) > dt_col and row[dt_col]:
        ym = _YEAR_RE.search(str(row[dt_col]))
        if ym:
            yr = int(ym.group())
    if yr is not None and yr < YEAR_CUTOFF:
        skip["YEAR"] += 1
        continue

    if not tx or len(tx) < 30:
        continue

    cls = classify(tx, "TIMES_L2")
    if cls.skip_cefr:
        key = "BRIEF" if cls.article_type.value == "BRIEF" else "DIALOGUE"
        skip[key] += 1
        continue

    res = measure(tx)
    results.append((res.c1plus_pct, res.not_word_hits, ttl[:60], res.total_words, res.c1_count, res.c2_count))
    print(".", end="", flush=True)

print(" 완료\n")

print(f"TIMES L2 전체: {total_l2}건")
print(f"제외 — 섹션EXCL={skip['EXCLUDE_SEC']}, 연도<{YEAR_CUTOFF}: {skip['YEAR']}, BRIEF={skip['BRIEF']}, DIALOGUE={skip['DIALOGUE']}")
print(f"분석 대상: {len(results)}건\n")

if not results:
    print("결과 없음")
    sys.exit(0)

ratios = [r[0] for r in results]
print("─" * 50)
print("C1+ 비율 분포 (TIMES_L2 현행 ARTICLE 풀)")
print("─" * 50)
print(f"  p10 = {pct(ratios, 10):.1f}%")
print(f"  p25 = {pct(ratios, 25):.1f}%")
print(f"  p50 = {pct(ratios, 50):.1f}%")
print(f"  p75 = {pct(ratios, 75):.1f}%")
print(f"  p90 = {pct(ratios, 90):.1f}%")
print(f"  min = {min(ratios):.1f}%  max = {max(ratios):.1f}%")
avg = sum(ratios) / len(ratios)
print(f"  avg = {avg:.1f}%")

# NOT 단어 집계
not_total:    dict[str, int] = {w: 0 for w in NOT_WORDS}
not_articles: dict[str, int] = {w: 0 for w in NOT_WORDS}
for _, not_hits, *_ in results:
    for w, cnt in not_hits.items():
        not_total[w]    = not_total.get(w, 0) + cnt
        not_articles[w] = not_articles.get(w, 0) + 1

print("\nNOT 단어 출현 (전체 분석 기사 중):")
for w in NOT_WORDS:
    tot  = not_total.get(w, 0)
    arts = not_articles.get(w, 0)
    mark = " ← 출현" if tot > 0 else ""
    print(f"  {w:<18}: {tot}회 ({arts}건){mark}")

# 하위/상위 5건
sorted_r = sorted(results, key=lambda x: x[0])
print("\n하위 5건 (C1+ 낮음):")
for c1pct, _, ttl, total, c1, c2 in sorted_r[:5]:
    print(f"  {c1pct:5.1f}%  total={total:3d}  C1={c1}  C2={c2}  {ttl}")

print("\n상위 5건 (C1+ 높음):")
for c1pct, _, ttl, total, c1, c2 in sorted_r[-5:]:
    print(f"  {c1pct:5.1f}%  total={total:3d}  C1={c1}  C2={c2}  {ttl}")
