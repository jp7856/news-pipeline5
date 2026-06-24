"""TIMES Star 섹션 avg_wc 분포 + 샘플 미리보기."""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import openpyxl

wb  = openpyxl.load_workbook(r"C:\Users\jp\Desktop\기사\articles.xlsx", read_only=True, data_only=True)
ws  = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
sec_col = next(i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower())
tx_col  = next(i for i,h in enumerate(hdr) if "본문" in h or "text" in h.lower())
ttl_col = next((i for i,h in enumerate(hdr) if "제목" in h or "title" in h.lower()), None)

star_articles = []
for row in rows[1:]:
    if not row or len(row) <= max(sec_col, tx_col): continue
    sec = str(row[sec_col]).strip() if row[sec_col] else ""
    txt = str(row[tx_col]).strip() if row[tx_col] else ""
    ttl = str(row[ttl_col]).strip() if (ttl_col and row[ttl_col]) else ""
    if sec != "Star" or len(txt) < 20: continue
    wc = len(re.findall(r"[A-Za-z']+", txt))
    star_articles.append((wc, ttl, txt))

star_articles.sort(key=lambda x: x[0])
n = len(star_articles)

# 분포 버킷
buckets = [(0,60),(60,100),(100,150),(150,200),(200,9999)]
print(f"Star 섹션 전체 {n}건 — avg_wc 분포")
print(f"{'─'*40}")
for lo, hi in buckets:
    cnt = sum(1 for wc,_,_ in star_articles if lo <= wc < hi)
    bar = "█" * (cnt // 10)
    label = f"{lo}–{hi-1}" if hi < 9999 else f"{lo}+"
    print(f"  {label:>8}단어: {cnt:>4}건  {bar}")

# 사분위
def p(xs, pct): return xs[min(int(len(xs)*pct/100), len(xs)-1)]
wcs = [w for w,_,_ in star_articles]
print(f"\n  p10={p(wcs,10)}  p25={p(wcs,25)}  p50={p(wcs,50)}  p75={p(wcs,75)}  p90={p(wcs,90)}")

# 구간별 샘플 1건씩
print(f"\n{'─'*60}")
print("구간별 샘플 미리보기 (본문 200자)")
for lo, hi in [(0,80),(80,130),(130,200)]:
    group = [(wc,ttl,txt) for wc,ttl,txt in star_articles if lo <= wc < hi]
    if not group: continue
    wc, ttl, txt = group[len(group)//2]
    preview = txt[:200].replace("\n", " ")
    print(f"\n[{lo}–{hi-1}단어 구간] wc={wc}  제목: {ttl[:60] or '(없음)'}")
    print(f"  {preview}...")
