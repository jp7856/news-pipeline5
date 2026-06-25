"""TIMES_L2 avg_min 통과 + FK 낮은 기사 5건 전문 출력."""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import textstat
import openpyxl
from agents.sub_agents.cefr_checker import validate
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
AVG_MIN = 13.5
FK_CEILING = 8.0   # 이 이하 기사만 대상

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
lv_col = next(i for i,h in enumerate(hdr) if "레벨" in h or "level"   in h.lower())
tx_col = next(i for i,h in enumerate(hdr) if "본문" in h or "text"    in h.lower())
sc_col = next(i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower())

suspects: list[tuple] = []  # (avg, fk, sec, txt)

for row in rows[1:]:
    if not row or len(row) <= max(lv_col, tx_col, sc_col): continue
    lv  = str(row[lv_col]).strip() if row[lv_col] else ""
    txt = str(row[tx_col]).strip() if row[tx_col] else ""
    sec = str(row[sc_col]).strip() if row[sc_col] else ""
    if not lv or len(txt) < 50: continue
    if sec in EXCLUDE_SECTIONS: continue
    wc = len(re.findall(r"[A-Za-z']+", txt))
    if wc < 100: continue
    m = re.search(r"\d+", lv)
    if not m or f"TIMES_L{m.group()}" != "TIMES_L2": continue
    if classify(txt, "TIMES_L2").skip_cefr: continue

    avg = validate(txt, "TIMES_L2").avg_sentence_len
    if avg < AVG_MIN: continue
    fk = textstat.flesch_kincaid_grade(txt)
    if fk >= FK_CEILING: continue
    suspects.append((avg, fk, sec, txt))

# FK 오름차순 → 가장 낮은 것부터, 단 섹션 겹치지 않게 다양하게 5건
suspects.sort(key=lambda x: x[1])

seen_secs: set[str] = set()
picks: list[tuple] = []
for item in suspects:
    sec = item[2]
    if sec not in seen_secs:
        picks.append(item)
        seen_secs.add(sec)
    if len(picks) == 5:
        break

# 섹션 다양성으로 5건이 안 차면 그냥 FK 낮은 순으로 보충
if len(picks) < 5:
    for item in suspects:
        if item not in picks:
            picks.append(item)
        if len(picks) == 5:
            break

print(f"TIMES_L2 avg_min({AVG_MIN}) 통과 + FK < {FK_CEILING} 기사 5건 전문")
print(f"총 해당 기사: {len(suspects)}건\n")

for i, (avg, fk, sec, txt) in enumerate(picks, 1):
    wc = len(re.findall(r"[A-Za-z']+", txt))
    print("=" * 72)
    print(f"[{i}]  섹션: {sec}  |  avg={avg:.1f}  FK={fk:.1f}  wc={wc}")
    print("=" * 72)
    print(txt)
    print()
