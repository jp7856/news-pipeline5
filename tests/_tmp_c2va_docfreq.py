"""
TIMES_L2 코퍼스 전체 C2 동사·부사 → 출현 기사 수 + 코퍼스 빈도 집계.
cefrpy data.bin에는 주파수 없음 — 두 신호 모두 코퍼스에서 직접 계산.
  신호A: doc_freq  = 기사 몇 개에 등장 (높을수록 여러 기사에 퍼짐 = 분석어 후보)
  신호B: corp_freq = 코퍼스 전체 등장 횟수 (토큰, dedup 없이)
판단·임계값 없음.
"""
import sys, io, re, collections
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

# ── 로딩 ─────────────────────────────────────────────────────────────────────
EXCLUDE = {
    "Photo News","Briefs","Star Brief","News in Brief","Cartoon",
    "Did You Know","Did You Know?","Debating","Cover","Q & A",
    "NE You","My Journal","Book Review","Stories","Story",
    "Readings for Junior","VoA Broadcast News","Think About It","My Diary","Debate",
}

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
def ci(p): return next((i for i,h in enumerate(hdr) if p in h or p.lower() in h.lower()), None)
lv_col, tx_col, sc_col, iss_col = ci("레벨"), ci("본문"), ci("섹션"), ci("호수")
def gc(r, c):
    if c is None or len(r) <= c or r[c] is None: return ""
    return str(r[c]).strip()

# ── 코퍼스 스캔 — 연도 무관 전체 ──────────────────────────────────────────────
# word → set of article_id (iss+"_"+sc)
doc_sets:   dict[str, set]  = collections.defaultdict(set)
# word → total raw token count (dedup 없음)
corp_freq:  dict[str, int]  = collections.defaultdict(int)
# POS 태그
word_cat:   dict[str, str]  = {}
total_arts = 0

print("스캔 중 (연도 무관 전체)...", end="", flush=True)

for row in rows[1:]:
    if not row: continue
    if re.sub(r'[^0-9]', '', gc(row, lv_col)) != "2": continue
    sc  = gc(row, sc_col)
    tx  = gc(row, tx_col)
    iss = gc(row, iss_col)
    if sc in EXCLUDE or not tx or len(tx) < 30: continue
    cls = classify(tx, "TIMES_L2")
    if cls.skip_cefr: continue

    art_id = f"{iss}_{sc}"
    total_arts += 1

    # dedup: 기사 내 처음 등장만 doc_sets에 추가, corp_freq는 토큰마다 +1
    seen_in_art: set[str] = set()
    for sent in _SENT_SPLIT.split(tx.strip()):
        for i, raw in enumerate(re.findall(r'[A-Za-z]+', sent)):
            if raw[0].isupper() and i > 0: continue
            w = raw.lower()
            if len(w) <= 2 or w in DOMAIN_TERMS: continue
            lv = get_cefr(w)
            if lv != "C2": continue
            cat = _c2_cat(w)
            if cat not in ("동사", "부사"): continue
            corp_freq[w] += 1
            word_cat[w] = cat
            if w not in seen_in_art:
                seen_in_art.add(w)
                doc_sets[w].add(art_id)

    print(".", end="", flush=True)

print(f" 완료  (총 {total_arts}건 기사)\n")

# ── 집계 ─────────────────────────────────────────────────────────────────────
# (word, doc_freq, corp_freq, cat) 테이블
table = [
    (w, len(doc_sets[w]), corp_freq[w], word_cat[w])
    for w in doc_sets
]
table.sort(key=lambda x: x[1])   # doc_freq 오름차순

n_words = len(table)
# doc_freq 분포 파악
all_df = [r[1] for r in table]
def pct(xs, p):
    s = sorted(xs)
    return s[min(int(len(s)*p/100), len(s)-1)]

p25v = pct(all_df, 25)
p50v = pct(all_df, 50)
p75v = pct(all_df, 75)
p90v = pct(all_df, 90)

print("=" * 70)
print(f"C2 동사·부사 고유 단어 수: {n_words}개  |  총 코퍼스: {total_arts}건 기사")
print(f"doc_freq 분포: p25={p25v}  p50={p50v}  p75={p75v}  p90={p90v}")
print("=" * 70)

# ── (a) 토픽어 후보: doc_freq ≤ p25 (소수 기사에만 등장) ──────────────────────
topic_cands = [r for r in table if r[1] <= p25v]
analytic_cands = [r for r in table if r[1] >= p75v]

print(f"\n(a) 토픽어 후보  — doc_freq ≤ {p25v}개 기사  ({len(topic_cands)}개 단어)")
print(f"    형식: 단어[품사]  출현기사수  코퍼스횟수")
print("    " + "-"*60)
# 코퍼스 빈도 내림차순으로 상위 40개 샘플
for w, df, cf, cat in sorted(topic_cands, key=lambda x: -x[2])[:40]:
    print(f"    {w}[{cat}]  doc={df}  corp={cf}")

print(f"\n(b) 분석어 후보  — doc_freq ≥ {p75v}개 기사  ({len(analytic_cands)}개 단어)")
print("    " + "-"*60)
# 문서빈도 내림차순
for w, df, cf, cat in sorted(analytic_cands, key=lambda x: -x[1])[:40]:
    print(f"    {w}[{cat}]  doc={df}  corp={cf}")

# ── 검증: 10개 타겟 단어 ─────────────────────────────────────────────────────
VERIFY = [
    # 토픽어 의심
    "broods", "decompose", "sap", "cacao", "encapsulate",
    # 분석어 의심
    "contend", "conducted", "escalate", "preemptively", "loitering",
]

print("\n\n" + "=" * 70)
print("검증: 10개 타겟 단어 — doc_freq / corp_freq / 분류 위치")
print("=" * 70)
lookup = {w: (df, cf, cat) for w,df,cf,cat in table}

for w in VERIFY:
    if w in lookup:
        df, cf, cat = lookup[w]
        # doc_freq 백분위
        dp = round(sum(1 for x in all_df if x <= df) / n_words * 100, 0)
        tier = "토픽후보" if df <= p25v else ("분석후보" if df >= p75v else "중간")
        print(f"  {w:<18} [{cat}]  doc={df:3d}({dp:4.0f}%ile)  corp={cf:4d}  → {tier}")
    else:
        # lemmatize해서 다시 찾기
        found = False
        for lemma in _get_candidates(w):
            if lemma in lookup:
                df, cf, cat = lookup[lemma]
                dp = round(sum(1 for x in all_df if x <= df) / n_words * 100, 0)
                tier = "토픽후보" if df <= p25v else ("분석후보" if df >= p75v else "중간")
                print(f"  {w:<18} → lemma={lemma}  [{cat}]  doc={df:3d}({dp:4.0f}%ile)  corp={cf:4d}  → {tier}")
                found = True
                break
        if not found:
            # C2가 아니거나 동사·부사 아님 (C1 or not in corpus)
            lv = get_cefr(w)
            cat = _c2_cat(w)
            print(f"  {w:<18} → C2VA 집계 미포함 (level={lv}, cat={cat})")

# ── 전체 테이블 (doc_freq=1~5 구간 vs 10+ 구간 비교) ─────────────────────────
print("\n\n" + "=" * 70)
print("doc_freq 구간별 단어 수 분포")
print("=" * 70)
buckets = collections.Counter()
for _, df, _, _ in table:
    if df == 1:     buckets["1"] += 1
    elif df <= 2:   buckets["2"] += 1
    elif df <= 5:   buckets["3-5"] += 1
    elif df <= 10:  buckets["6-10"] += 1
    elif df <= 20:  buckets["11-20"] += 1
    else:           buckets["21+"] += 1

for k in ["1","2","3-5","6-10","11-20","21+"]:
    bar = "█" * buckets[k]
    print(f"  doc_freq={k:>5}  {buckets[k]:4d}개  {bar}")
