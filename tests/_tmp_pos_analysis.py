"""
C1/C2 단어 품사(POS)별 분류 — 5개 기사 비교
CCTV 767호 vs Science 4건(T-rex/로봇/매미/비행)
"""
import sys, io, re, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl
import cefrpy
from agents.sub_agents.vocab_checker import (
    DOMAIN_TERMS, _SENT_SPLIT, _TOKEN, _get_candidates, _lookup
)
from agents.sub_agents.article_classifier import classify

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"

_analyzer = cefrpy.CEFRAnalyzer()
_CEFR_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2"]

# ── POS 카테고리 매핑 ─────────────────────────────────────────────────────────
VERB_IDS  = {p.value for p in cefrpy.POSTag if p.name in ("VB","VBD","VBG","VBN","VBP","VBZ")}
NOUN_IDS  = {p.value for p in cefrpy.POSTag if p.name in ("NN","NNS")}
ADJ_IDS   = {p.value for p in cefrpy.POSTag if p.name in ("JJ","JJR","JJS")}
ADV_IDS   = {p.value for p in cefrpy.POSTag if p.name in ("RB","RBR","RBS")}
PROP_IDS  = {p.value for p in cefrpy.POSTag if p.name in ("NNP","NNPS")}

def pos_category(word: str) -> str:
    """C1/C2로 매겨지는 POS 중 우선순위가 높은 카테고리 반환.
    우선순위: 동사 > 부사 > 형용사 > 명사 > 고유명사 > 기타
    (분석적 성격이 강한 품사를 앞에 둬 드리프트 검증에 유리하게)
    """
    for lemma in _get_candidates(word):
        if not _analyzer.is_word_in_database(lemma):
            continue
        cats: dict[str, str] = {}   # category → level
        for pos in cefrpy.POSTag:
            try:
                lv = _analyzer.get_word_pos_level_CEFR(lemma, pos)
                if lv is None:
                    continue
                s = str(lv).strip()
                if s not in ("C1", "C2"):
                    continue
                pid = pos.value
                if pid in VERB_IDS:
                    cats["동사"] = s
                elif pid in ADV_IDS:
                    cats["부사"] = s
                elif pid in ADJ_IDS:
                    cats["형용사"] = s
                elif pid in NOUN_IDS:
                    cats["명사"] = s
                elif pid in PROP_IDS:
                    cats["고유명사"] = s
                else:
                    cats["기타"] = s
            except Exception:
                pass
        if cats:
            for cat in ("동사", "부사", "형용사", "명사", "고유명사", "기타"):
                if cat in cats:
                    return cat
    return "기타"


def get_cefr_and_pos(word: str) -> tuple[str | None, str]:
    """(레벨, 품사카테고리) 반환. 미수록이면 (None, '')."""
    w = word.lower()
    for lemma in _get_candidates(w):
        lv = _lookup(lemma)
        if lv is not None:
            cat = pos_category(w)
            return lv, cat
    return None, ""


def extract_c1c2(text: str) -> list[tuple[str, str, str]]:
    """(word, level, pos_category) 리스트 반환. dedup 적용."""
    seen: set[str] = set()
    result = []
    for sent in _SENT_SPLIT.split(text.strip()):
        tokens = _TOKEN.findall(sent)
        for i, raw in enumerate(tokens):
            if raw[0].isupper() and i > 0:
                continue
            w = raw.lower()
            if len(w) <= 2:
                continue
            if w in DOMAIN_TERMS:
                continue
            if w in seen:
                continue
            seen.add(w)
            lv, cat = get_cefr_and_pos(w)
            if lv in ("C1", "C2"):
                result.append((w, lv, cat))
    return result


# ── 기사 로딩 ─────────────────────────────────────────────────────────────────
TARGET_ISS = {"767", "978", "1045", "980", "1022"}
TARGET_LABELS = {
    "767":  "CCTV 767호 [Science/2020]",
    "978":  "T-rex 978호 [Science/2024]",
    "1045": "로봇 1045호 [Science/2025]",
    "980":  "매미 980호 [Science/2024]",
    "1022": "비행 1022호 [Science/2025]",
}
EXCLUDE_SECTIONS = {
    "Photo News","Briefs","Star Brief","News in Brief","Cartoon",
    "Did You Know","Did You Know?","Debating","Cover","Q & A",
    "NE You","My Journal","Book Review","Stories","Story",
    "Readings for Junior","VoA Broadcast News","Think About It","My Diary","Debate",
}

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]

lv_col  = next((i for i,h in enumerate(hdr) if "레벨"  in h or "level"   in h.lower()), None)
tx_col  = next((i for i,h in enumerate(hdr) if "본문"  in h or "text"    in h.lower()), None)
sc_col  = next((i for i,h in enumerate(hdr) if "섹션"  in h or "section" in h.lower()), None)
iss_col = next((i for i,h in enumerate(hdr) if "호수"  in h or "issue"   in h.lower()), None)
dt_col  = next((i for i,h in enumerate(hdr) if "날짜"  in h or "date"    in h.lower()), None)

def gc(row, col):
    if col is None or len(row) <= col or row[col] is None:
        return ""
    return str(row[col]).strip()

articles: dict[str, tuple[str, str]] = {}   # iss → (tx, dt)
for row in rows[1:]:
    if not row: continue
    iss = gc(row, iss_col)
    if iss not in TARGET_ISS: continue
    lv_raw = gc(row, lv_col)
    if re.sub(r'[^0-9]', '', lv_raw) != "2": continue
    sc = gc(row, sc_col)
    tx = gc(row, tx_col)
    dt = gc(row, dt_col)
    if sc in EXCLUDE_SECTIONS: continue
    if not tx or len(tx) < 30: continue
    cls = classify(tx, "TIMES_L2")
    if cls.skip_cefr: continue
    # 같은 호수에 여러 기사가 있을 수 있음 — 767호는 CCTV 본문만
    if iss == "767" and "CCTV" not in tx and "surveillance" not in tx.lower():
        continue
    if iss not in articles:
        articles[iss] = (tx, dt)

print(f"로딩된 기사: {list(articles.keys())}\n")

# ── POS 분석 출력 ─────────────────────────────────────────────────────────────
# 출력 순서
ORDER = ["767", "978", "1045", "980", "1022"]

# 구체명사 vs 추상명사 판단 기준 (휴리스틱)
# 형태가 있거나 직접 관찰 가능한 개체 → 구체
CONCRETE_NOUNS = {
    # 생물·자연
    "cicada","cicadas","larvae","nymph","dinosaur","tyrannosaurus","rex","creature",
    "pterosaur","pollen","sap","clay","silt",
    # 기계·사물
    "robot","robots","drone","drones","propeller","replica","prototype","cctv",
    "vehicle","vehicles","elytra","beetle","grasshopper","dragonfly",
    # 음식·문화
    "croissant","pastry","confection","vanilla","cicadas",
    # 장소·물체
    "terrain","perimeter","footage",
}

def noun_type(w: str) -> str:
    if w in CONCRETE_NOUNS:
        return "(구체)"
    return "(추상)"


print("=" * 72)
print("C1/C2 단어 품사별 분류")
print("형식: 단어[레벨] — 명사는 (구체)/(추상) 표시")
print("=" * 72)

summary_rows = []   # 기사별 요약 집계용

for iss in ORDER:
    label = TARGET_LABELS.get(iss, iss)
    if iss not in articles:
        print(f"\n▌ {label}  — 기사 없음\n")
        continue

    tx, dt = articles[iss]
    words = extract_c1c2(tx)

    # 품사별 분류
    by_pos: dict[str, list[tuple[str,str]]] = {
        "동사": [], "부사": [], "형용사": [], "명사": [], "기타": []
    }
    for w, lv, cat in words:
        by_pos.get(cat, by_pos["기타"]).append((w, lv))

    total_c1c2 = len(words)
    verb_n = len(by_pos["동사"])
    adv_n  = len(by_pos["부사"])
    adj_n  = len(by_pos["형용사"])
    noun_n = len(by_pos["명사"])

    # 명사 중 추상 비율
    abstract_nouns = [w for w,lv in by_pos["명사"] if noun_type(w) == "(추상)"]
    concrete_nouns = [w for w,lv in by_pos["명사"] if noun_type(w) == "(구체)"]

    print(f"\n{'─'*72}")
    print(f"▌ {label}")
    print(f"  C1/C2 단어 합계: {total_c1c2}개  "
          f"(동사={verb_n} 부사={adv_n} 형용사={adj_n} 명사={noun_n} 기타={len(by_pos['기타'])})")
    print(f"{'─'*72}")

    for cat in ("동사", "부사", "형용사", "명사", "기타"):
        items = by_pos[cat]
        if not items:
            continue
        print(f"\n  [{cat}]")
        for w, lv in sorted(items, key=lambda x: (x[1], x[0])):
            if cat == "명사":
                nt = noun_type(w)
                print(f"    {w}[{lv}] {nt}")
            else:
                print(f"    {w}[{lv}]")

    # 분석 지표 계산
    analytic_n = verb_n + adv_n + len(abstract_nouns)
    topic_n    = len(concrete_nouns) + adj_n
    print(f"\n  분석어(동사+부사+추상명사): {analytic_n}/{total_c1c2}  "
          f"토픽어(구체명사+형용사): {topic_n}/{total_c1c2}")

    summary_rows.append((label, total_c1c2, verb_n, adv_n, adj_n,
                         len(concrete_nouns), len(abstract_nouns), analytic_n, topic_n))

# ── 요약 비교표 ────────────────────────────────────────────────────────────────
print("\n\n" + "=" * 72)
print("요약 비교표")
print(f"  {'기사':<30}  {'C1/C2':>6}  {'동사':>4}  {'부사':>4}  {'형용사':>4}  "
      f"{'구체명사':>6}  {'추상명사':>6}  {'분석어':>5}  {'토픽어':>5}")
print("  " + "-"*70)
for row in summary_rows:
    label, tot, vb, adv, adj, conc, abst, analytic, topic = row
    print(f"  {label:<30}  {tot:>6}  {vb:>4}  {adv:>4}  {adj:>4}  "
          f"{conc:>6}  {abst:>6}  {analytic:>5}  {topic:>5}")
