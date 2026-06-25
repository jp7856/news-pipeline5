"""TIMES_L2 avg 13.5~14.5 구간 샘플 — 13.5로 내리면 통과, 14.5면 거부되는 기사."""
import sys, io, re, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import openpyxl
from agents.sub_agents.cefr_checker import validate
from agents.sub_agents.article_classifier import classify, ArticleType

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"
EXCLUDE_SECTIONS = {
    "Photo News", "Briefs", "Star Brief", "News in Brief",
    "Cartoon", "Did You Know", "Did You Know?", "Debating", "Cover", "Q & A",
}
MIN_WC = 100

wb   = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws   = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
lv_col  = next(i for i,h in enumerate(hdr) if "레벨" in h or "level" in h.lower())
tx_col  = next(i for i,h in enumerate(hdr) if "본문" in h or "text" in h.lower())
sc_col  = next(i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower())
ttl_col = next((i for i,h in enumerate(hdr) if "제목" in h or "title" in h.lower()), None)

boundary = []  # avg 13.5~14.5 구간 ARTICLE만

for row in rows[1:]:
    if not row or len(row) <= max(lv_col, tx_col): continue
    lv  = str(row[lv_col]).strip() if row[lv_col] else ""
    txt = str(row[tx_col]).strip() if row[tx_col] else ""
    sec = str(row[sc_col]).strip() if row[sc_col] else ""
    ttl = str(row[ttl_col]).strip() if (ttl_col and row[ttl_col]) else ""
    if lv != "LEVEL 2": continue
    if sec in EXCLUDE_SECTIONS: continue
    wc = len(re.findall(r"[A-Za-z']+", txt))
    if wc < MIN_WC: continue
    if classify(txt, "TIMES_L2").skip_cefr: continue

    avg = validate(txt, "TIMES_L2").avg_sentence_len
    if 13.5 <= avg < 14.5:
        boundary.append((avg, sec, ttl, txt))

random.seed(7)
sample = random.sample(boundary, min(10, len(boundary)))
sample.sort(key=lambda x: x[0])

print(f"TIMES_L2 avg 13.5~14.5 구간: 총 {len(boundary)}건 → 샘플 {len(sample)}건")
print(f"(avg_min=14.5면 전부 거부 / 13.5로 내리면 전부 통과)")
print()

for i, (avg_v, sec, ttl, txt) in enumerate(sample, 1):
    # 문장별 길이 계산 (패턴 확인용)
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', txt) if len(s.strip()) > 10]
    sent_lens = [len(re.findall(r"[A-Za-z']+", s)) for s in sentences]
    short = sum(1 for l in sent_lens if l <= 10)
    long_ = sum(1 for l in sent_lens if l >= 20)

    print(f"{'='*70}")
    print(f"[{i}] avg={avg_v:.2f}  섹션={sec}  단문(≤10w)={short}개 장문(≥20w)={long_}개")
    print(f"     제목: {ttl[:80]}")
    print()
    # 본문 전체 출력 (최대 600자)
    body = txt[:600].replace("\n\n", "\n").strip()
    print(body)
    if len(txt) > 600:
        print(f"  ... [+{len(txt)-600}자 생략]")
    print()
