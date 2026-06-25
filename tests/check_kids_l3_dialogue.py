"""KIDS_L3 DIALOGUE 분류 샘플 확인 — 진짜 대화체 vs false positive."""
import sys, io, re, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import openpyxl
from agents.sub_agents.article_classifier import classify, ArticleType, _is_speaker_line

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"
EXCLUDE_SECTIONS = {
    "Photo News", "Briefs", "Star Brief", "News in Brief",
    "Cartoon", "Did You Know", "Did You Know?", "Debating", "Cover", "Q & A",
    "NE You",
}
MIN_WC = 50  # KIDS 기준

wb   = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws   = wb["KIDS"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
lv_col  = next(i for i,h in enumerate(hdr) if "레벨" in h or "level" in h.lower())
tx_col  = next(i for i,h in enumerate(hdr) if "본문" in h or "text" in h.lower())
sc_col  = next(i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower())
ttl_col = next((i for i,h in enumerate(hdr) if "제목" in h or "title" in h.lower()), None)

dialogues = []  # (sec, title, wc, ratio, speaker_lines, text)

for row in rows[1:]:
    if not row or len(row) <= max(lv_col, tx_col): continue
    lv  = str(row[lv_col]).strip() if row[lv_col] else ""
    txt = str(row[tx_col]).strip() if row[tx_col] else ""
    sec = str(row[sc_col]).strip() if row[sc_col] else ""
    ttl = str(row[ttl_col]).strip() if (ttl_col and row[ttl_col]) else ""
    if lv != "LEVEL 3": continue
    if sec in EXCLUDE_SECTIONS: continue
    wc = len(re.findall(r"[A-Za-z']+", txt))
    if wc < MIN_WC: continue

    cls = classify(txt, "KIDS_L3")
    if cls.article_type != ArticleType.DIALOGUE: continue

    # 감지된 화자줄 수집
    speaker_lines = [line for line in txt.splitlines() if _is_speaker_line(line)[0]]
    dialogues.append((sec, ttl, wc, cls.dialogue_line_ratio, speaker_lines, txt))

print(f"KIDS_L3 DIALOGUE 총 {len(dialogues)}건 — 섹션 분포:")
sec_dist: dict[str, int] = {}
for sec, *_ in dialogues:
    sec_dist[sec] = sec_dist.get(sec, 0) + 1
for sec, cnt in sorted(sec_dist.items(), key=lambda x: -x[1]):
    print(f"  {sec:<30} {cnt}건")

print()
print("=" * 70)
print("샘플 10건 (무작위)")
print("=" * 70)

random.seed(42)
sample = random.sample(dialogues, min(10, len(dialogues)))
# 비율 낮은 것 → 높은 것 순으로 정렬 (false positive 후보부터 보기)
sample.sort(key=lambda x: x[3])

for i, (sec, ttl, wc, ratio, sp_lines, txt) in enumerate(sample, 1):
    print(f"\n[{i}] 섹션={sec}  wc={wc}  화자줄비율={ratio:.0%}  화자줄수={len(sp_lines)}")
    print(f"    제목: {ttl[:80]}")
    print(f"    감지된 화자줄:")
    for sl in sp_lines[:5]:
        print(f"      > {sl[:90]}")
    if len(sp_lines) > 5:
        print(f"      ... 외 {len(sp_lines)-5}줄")
    print(f"    본문 앞 200자:")
    preview = txt[:200].replace("\n", " / ")
    print(f"      {preview}...")
    print("─" * 70)
