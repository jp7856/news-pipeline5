"""
C2VA >= 4.76% (CCTV 767호 기준) 기사 전체 목록 — 2024+, dedup
출력: C2VA% / 섹션 / C2 동사·부사 목록 / 본문 앞 150자
판단 없음.
"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl
import cefrpy
from agents.sub_agents.vocab_checker import DOMAIN_TERMS, _SENT_SPLIT, _TOKEN, _get_candidates, get_cefr
from agents.sub_agents.article_classifier import classify

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"
_analyzer = cefrpy.CEFRAnalyzer()

VERB_IDS = {p.value for p in cefrpy.POSTag if p.name in ("VB","VBD","VBG","VBN","VBP","VBZ")}
ADV_IDS  = {p.value for p in cefrpy.POSTag if p.name in ("RB","RBR","RBS")}
_pos_cache: dict[str, str] = {}

def _c2_cat(word: str) -> str:
    if word in _pos_cache:
        return _pos_cache[word]
    cat = "기타"
    for lemma in _get_candidates(word):
        if not _analyzer.is_word_in_database(lemma):
            continue
        found = set()
        for pos in cefrpy.POSTag:
            try:
                lv = _analyzer.get_word_pos_level_CEFR(lemma, pos)
                if lv is None: continue
                if str(lv).strip() not in ("C1", "C2"): continue
                if pos.value in VERB_IDS: found.add("동사")
                elif pos.value in ADV_IDS: found.add("부사")
            except Exception:
                pass
        if found:
            cat = "동사" if "동사" in found else "부사"
        break
    _pos_cache[word] = cat
    return cat

def scan(text: str):
    seen: set[str] = set()
    total = c2va = 0
    words: list[str] = []
    for sent in _SENT_SPLIT.split(text.strip()):
        for i, raw in enumerate(re.findall(r'[A-Za-z]+', sent)):
            if raw[0].isupper() and i > 0: continue
            w = raw.lower()
            if len(w) <= 2 or w in DOMAIN_TERMS or w in seen: continue
            seen.add(w)
            lv = get_cefr(w)
            if lv is None: continue
            total += 1
            if lv == "C2" and _c2_cat(w) in ("동사", "부사"):
                c2va += 1
                words.append(w)
    pct = round(c2va / total * 100, 2) if total else 0.0
    return pct, total, words

# ── 로딩 ─────────────────────────────────────────────────────────────────────
EXCLUDE = {
    "Photo News","Briefs","Star Brief","News in Brief","Cartoon",
    "Did You Know","Did You Know?","Debating","Cover","Q & A",
    "NE You","My Journal","Book Review","Stories","Story",
    "Readings for Junior","VoA Broadcast News","Think About It","My Diary","Debate",
}
_YR = re.compile(r'\b(20\d{2})\b')

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
def ci(p): return next((i for i,h in enumerate(hdr) if p in h or p.lower() in h.lower()), None)
lv_col, tx_col, sc_col, dt_col, iss_col = ci("레벨"), ci("본문"), ci("섹션"), ci("날짜"), ci("호수")
def gc(r, c):
    if c is None or len(r) <= c or r[c] is None: return ""
    return str(r[c]).strip()

CCTV_THRESHOLD = 4.76

results = []
print("분석 중...", end="", flush=True)

for row in rows[1:]:
    if not row: continue
    if re.sub(r'[^0-9]', '', gc(row, lv_col)) != "2": continue
    sc  = gc(row, sc_col)
    tx  = gc(row, tx_col)
    dt  = gc(row, dt_col)
    iss = gc(row, iss_col)
    if sc in EXCLUDE or not tx or len(tx) < 30: continue
    ym = _YR.search(dt)
    yr = int(ym.group()) if ym else None
    if yr is not None and yr < 2024: continue
    cls = classify(tx, "TIMES_L2")
    if cls.skip_cefr: continue
    pct, total, words = scan(tx)
    if pct >= CCTV_THRESHOLD:
        results.append((pct, total, words, sc, iss, dt, tx.strip()[:150]))
    print(".", end="", flush=True)

results.sort(key=lambda x: -x[0])
print(f" 완료\n")

print("=" * 78)
print(f"C2VA >= {CCTV_THRESHOLD}% 기사 — TIMES_L2 2024+, dedup  (총 {len(results)}건)")
print(f"CCTV 767호 기준: 4.76% / C2 동사·부사: loitering trespassing sift pinpoint drones / preemptively")
print("=" * 78)

for rank, (pct, total, words, sc, iss, dt, prev) in enumerate(results, 1):
    print(f"\n#{rank:02d}  C2VA={pct:.2f}%  [{sc}]  {iss} {dt}  (total={total})")
    print(f"  C2동사·부사: {', '.join(words)}")
    print(f"  {prev}")
