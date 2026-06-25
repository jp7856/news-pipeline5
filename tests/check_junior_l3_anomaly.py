"""JUNIOR_L3 역전 원인 분석 — 섹션 구성 / 하위 샘플 / 라벨 오류 가능성."""
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
MIN_WC = 80

wb   = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws   = wb["JUNIOR"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
lv_col  = next(i for i,h in enumerate(hdr) if "레벨" in h or "level"   in h.lower())
tx_col  = next(i for i,h in enumerate(hdr) if "본문" in h or "text"    in h.lower())
sc_col  = next(i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower())
ttl_col = next((i for i,h in enumerate(hdr) if "제목" in h or "title"  in h.lower()), None)

# ── 전체 로드 (필터 전) — 라벨 오류 확인용 ───────────────────────────────
raw_all: list[tuple[str,str,str,str,int,float]] = []  # (lv, sec, ttl, txt, wc, avg)

for row in rows[1:]:
    if not row or len(row) <= max(lv_col, tx_col): continue
    lv  = str(row[lv_col]).strip() if row[lv_col]  else ""
    txt = str(row[tx_col]).strip() if row[tx_col]  else ""
    sec = str(row[sc_col]).strip() if (sc_col and row[sc_col]) else ""
    ttl = str(row[ttl_col]).strip() if (ttl_col and row[ttl_col]) else ""
    if not lv or len(txt) < 50: continue
    wc  = len(re.findall(r"[A-Za-z']+", txt))
    num = re.search(r"\d+", lv)
    if not num: continue
    key = f"JUNIOR_L{num.group()}"
    if key not in LEVELS: continue
    avg = validate(txt, key).avg_sentence_len
    raw_all.append((lv, sec, ttl, txt, wc, avg))

# ── 필터 적용 후 L3 기사 ─────────────────────────────────────────────────
l3_clean: list[tuple[str,str,str,int,float]] = []   # (sec, ttl, txt, wc, avg)

for lv, sec, ttl, txt, wc, avg in raw_all:
    if lv != "LEVEL 3": continue
    if sec in EXCLUDE_SECTIONS: continue
    if wc < MIN_WC: continue
    if classify(txt, "JUNIOR_L3").skip_cefr: continue
    l3_clean.append((sec, ttl, txt, wc, avg))

l3_avgs = [avg for *_, avg in l3_clean]

def pct(xs, p):
    s = sorted(xs)
    return s[min(int(len(s)*p/100), len(s)-1)]

print("=" * 70)
print(f"(0) JUNIOR 시트 전체 레벨 분포 (라벨 오류 탐지)")
print("=" * 70)
lv_dist: dict[str, int] = {}
for lv, *_ in raw_all:
    lv_dist[lv] = lv_dist.get(lv, 0) + 1
for lv in sorted(lv_dist):
    print(f"  {lv:<15} {lv_dist[lv]}건")

print()
print("=" * 70)
print(f"(1) JUNIOR_L3 섹션 구성 (필터 후 {len(l3_clean)}건)")
print("=" * 70)
sec_stats: dict[str, list[float]] = {}
for sec, ttl, txt, wc, avg in l3_clean:
    sec_stats.setdefault(sec, []).append(avg)
print(f"  {'섹션':<28} {'건수':>5}  {'avg_p50':>8}  {'avg_min':>8}  {'avg_max':>8}")
print("  " + "─" * 60)
for sec in sorted(sec_stats, key=lambda s: -len(sec_stats[s])):
    avgs = sec_stats[sec]
    print(f"  {sec:<28} {len(avgs):>5}건  "
          f"{pct(avgs,50):>8.1f}  {min(avgs):>8.1f}  {max(avgs):>8.1f}")

print()
print("=" * 70)
print(f"(2) avg 하위 10건 샘플 (avg 오름차순, 필터 후)")
print("=" * 70)
bottom10 = sorted(l3_clean, key=lambda x: x[4])[:10]
for i, (sec, ttl, txt, wc, avg) in enumerate(bottom10, 1):
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', txt) if len(s.strip()) > 8]
    sent_lens = sorted([len(re.findall(r"[A-Za-z']+", s)) for s in sentences])
    short3 = sent_lens[:3]  # 가장 짧은 3문장 길이
    print(f"\n[{i}] avg={avg:.2f}  wc={wc}  섹션={sec}")
    print(f"     제목: {ttl[:80]}")
    print(f"     짧은 문장 상위3 단어수: {short3}")
    body = txt[:300].replace("\n", " / ").strip()
    print(f"     본문: {body}...")

print()
print("=" * 70)
print("(3) 라벨 오류 탐지 — JUNIOR L3 라벨인데 avg가 L1/L2 중앙값보다 낮은 기사")
print("=" * 70)
# L1 p50=12.2, L2 p50=12.7 — L3인데 avg < 10 이면 의심
l1_avgs = [avg for lv,_,_,_,_,avg in raw_all if lv=="LEVEL 1"]
l2_avgs = [avg for lv,_,_,_,_,avg in raw_all if lv=="LEVEL 2"]
l3_avgs_raw = [avg for lv,_,_,_,_,avg in raw_all if lv=="LEVEL 3"]

print(f"  전체 분포 (EXCLUDE_SECTIONS·wc 필터 전):")
for tag, xs in [("L1", l1_avgs), ("L2", l2_avgs), ("L3", l3_avgs_raw)]:
    if xs:
        print(f"  JUNIOR_{tag}: n={len(xs)}, p10={pct(xs,10):.1f}, "
              f"p50={pct(xs,50):.1f}, p90={pct(xs,90):.1f}")

# L3 라벨이지만 avg < 8 (KIDS 수준) 기사
suspect = [(lv,sec,ttl,txt,wc,avg) for lv,sec,ttl,txt,wc,avg in raw_all
           if lv == "LEVEL 3" and avg < 8.0]
print(f"\n  JUNIOR L3 라벨인데 avg < 8.0 (KIDS 수준): {len(suspect)}건")
for lv, sec, ttl, txt, wc, avg in sorted(suspect, key=lambda x: x[5])[:5]:
    print(f"    avg={avg:.2f}  wc={wc}  [{sec}]  {txt[:120].replace(chr(10),' ')}...")
