"""
섹션별 C2VA 상위 분포 샘플 출력 — 임계값 설정용.
C2VA p75 이상 기사 목록 (본문 앞 250자 + 단어 목록).
임계값·게이트 없음.
"""
import sys, io, re, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl
import cefrpy
from agents.sub_agents.vocab_checker import (
    DOMAIN_TERMS, _SENT_SPLIT, _TOKEN, _get_candidates, get_cefr
)
from agents.sub_agents.article_classifier import classify

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"
_analyzer = cefrpy.CEFRAnalyzer()

VERB_IDS = {p.value for p in cefrpy.POSTag if p.name in ("VB","VBD","VBG","VBN","VBP","VBZ")}
ADV_IDS  = {p.value for p in cefrpy.POSTag if p.name in ("RB","RBR","RBS")}
_c2pos_cache: dict[str, str] = {}

def _c2_cat(word: str) -> str:
    if word in _c2pos_cache:
        return _c2pos_cache[word]
    cat = "기타"
    for lemma in _get_candidates(word):
        if not _analyzer.is_word_in_database(lemma):
            continue
        found = set()
        for pos in cefrpy.POSTag:
            try:
                lv = _analyzer.get_word_pos_level_CEFR(lemma, pos)
                if lv is None: continue
                s = str(lv).strip()
                if s not in ("C1", "C2"): continue
                pid = pos.value
                if pid in VERB_IDS: found.add("동사")
                elif pid in ADV_IDS: found.add("부사")
            except Exception:
                pass
        if found:
            cat = "동사" if "동사" in found else "부사"
        break
    _c2pos_cache[word] = cat
    return cat

def measure_c2va(text: str) -> tuple[float, int, list[str]]:
    """(c2va_pct, total, c2va_words) 반환."""
    seen: set[str] = set()
    total = c2va = 0
    words: list[str] = []
    for sent in _SENT_SPLIT.split(text.strip()):
        toks = re.findall(r'[A-Za-z]+', sent)
        for i, raw in enumerate(toks):
            if raw[0].isupper() and i > 0: continue
            w = raw.lower()
            if len(w) <= 2: continue
            if w in DOMAIN_TERMS: continue
            if w in seen: continue
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
EXCLUDE_SECTIONS = {
    "Photo News","Briefs","Star Brief","News in Brief","Cartoon",
    "Did You Know","Did You Know?","Debating","Cover","Q & A",
    "NE You","My Journal","Book Review","Stories","Story",
    "Readings for Junior","VoA Broadcast News","Think About It","My Diary","Debate",
}
_YEAR_RE = re.compile(r'\b(20\d{2})\b')

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
def ci(p): return next((i for i,h in enumerate(hdr) if p in h or p.lower() in h.lower()), None)
lv_col, tx_col, sc_col, dt_col, iss_col = ci("레벨"), ci("본문"), ci("섹션"), ci("날짜"), ci("호수")
def gc(r, c):
    if c is None or len(r) <= c or r[c] is None: return ""
    return str(r[c]).strip()

# sec_rows[section] = [(c2va_pct, total, c2va_words, iss, dt, preview)]
sec_rows: dict[str, list] = collections.defaultdict(list)
print("분석 중...", end="", flush=True)

for row in rows[1:]:
    if not row: continue
    lv_raw = gc(row, lv_col)
    if re.sub(r'[^0-9]', '', lv_raw) != "2": continue
    sc  = gc(row, sc_col)
    tx  = gc(row, tx_col)
    dt  = gc(row, dt_col)
    iss = gc(row, iss_col)
    if sc in EXCLUDE_SECTIONS: continue
    ym = _YEAR_RE.search(dt)
    yr = int(ym.group()) if ym else None
    if yr is not None and yr < 2024: continue
    if not tx or len(tx) < 30: continue
    cls = classify(tx, "TIMES_L2")
    if cls.skip_cefr: continue
    pct_val, tot, words = measure_c2va(tx)
    prev = tx.strip()[:250].replace("\n", " ")
    sec_rows[sc].append((pct_val, tot, words, iss, dt, prev))
    print(".", end="", flush=True)

print(f" 완료\n")


def percentile(xs, p):
    if not xs: return 0.0
    s = sorted(xs)
    return s[min(int(len(s) * p / 100), len(s)-1)]

# 관심 섹션 우선 출력
SEC_ORDER = [
    "Headlines News", "Key Issue", "Science",
    "Read and Learn", "World", "Lifestyle", "Sports & Entertainment",
]
extras = sorted(s for s in sec_rows if s not in SEC_ORDER)
all_secs = [s for s in SEC_ORDER if s in sec_rows] + extras


for sec in all_secs:
    entries = sec_rows[sec]
    if not entries: continue

    vals = [e[0] for e in entries]
    p75v = percentile(vals, 75)
    p90v = percentile(vals, 90)

    # p75 이상인 기사만 (높은 순 상위 5개로 제한)
    top = sorted([e for e in entries if e[0] >= p75v], key=lambda x: -x[0])[:5]

    print("=" * 80)
    print(f"[{sec}]  n={len(entries)}  p75={p75v:.2f}%  p90={p90v:.2f}%  "
          f"  ★ p75 이상 {len([e for e in entries if e[0] >= p75v])}건 → 상위 5건 표시")
    print("=" * 80)

    for rank, (c2va, tot, words, iss, dt, prev) in enumerate(top, 1):
        print(f"\n  #{rank}  {iss} {dt}  C2VA={c2va:.2f}%  total={tot}")
        print(f"  C2 동사+부사: [{', '.join(words)}]")
        print(f"  {prev}")

    print()
