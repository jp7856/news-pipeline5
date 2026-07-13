"""
새 지표: C2 동사+C2 부사 비율 (dedup) vs 기존 C1+ 비율
목표 1) TIMES_L2 2024+ 섹션별 분포 (p50/p75/p90/p95, 두 지표 나란히)
목표 2) CCTV 767호 vs Science 토픽 4건 — 새 지표로 갈리는지 검증
목표 3) C2 동사로 잡힌 단어 중 형용사/명사 오분류 의심 케이스 집계
임계값·게이트 없음.
"""
import sys, io, re, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl
import cefrpy
from agents.sub_agents.vocab_checker import (
    DOMAIN_TERMS, _SENT_SPLIT, _TOKEN, _get_candidates, _lookup, get_cefr
)
from agents.sub_agents.article_classifier import classify

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"
_analyzer = cefrpy.CEFRAnalyzer()

# ── POS ID 집합 ───────────────────────────────────────────────────────────────
VERB_IDS       = {p.value for p in cefrpy.POSTag if p.name in ("VB","VBD","VBG","VBN","VBP","VBZ")}
ADV_IDS        = {p.value for p in cefrpy.POSTag if p.name in ("RB","RBR","RBS")}
ADJ_IDS        = {p.value for p in cefrpy.POSTag if p.name in ("JJ","JJR","JJS")}
NOUN_IDS       = {p.value for p in cefrpy.POSTag if p.name in ("NN","NNS")}
TRUE_VERB_IDS  = {p.value for p in cefrpy.POSTag if p.name in ("VB","VBD","VBP","VBZ")}
PART_IDS       = {p.value for p in cefrpy.POSTag if p.name in ("VBG","VBN")}

_c2pos_cache: dict[str, tuple[str, bool]] = {}  # word → (category, suspected)


def _c2_pos(word: str) -> tuple[str, bool]:
    """C2 단어의 품사 카테고리와 오분류 의심 여부 반환.
    suspected=True: VBG/VBN으로만 잡혔는데 JJ/NN 항목도 있음 → 형용사/명사 오분류 의심.
    """
    if word in _c2pos_cache:
        return _c2pos_cache[word]

    cat = "기타"
    suspected = False

    for lemma in _get_candidates(word):
        if not _analyzer.is_word_in_database(lemma):
            continue

        found: set[str] = set()
        has_true_verb = False
        has_part = False
        has_adj = False
        has_noun = False

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
                    found.add("동사")
                    if pid in TRUE_VERB_IDS:
                        has_true_verb = True
                    if pid in PART_IDS:
                        has_part = True
                elif pid in ADV_IDS:
                    found.add("부사")
                elif pid in ADJ_IDS:
                    found.add("형용사")
                    has_adj = True
                elif pid in NOUN_IDS:
                    found.add("명사")
                    has_noun = True
            except Exception:
                pass

        if found:
            for c in ("동사", "부사", "형용사", "명사"):
                if c in found:
                    cat = c
                    break
            # 오분류 의심 조건:
            # (1) 분사형(VBG/VBN)만으로 동사 판정됐고 adj/noun 항목도 존재
            # (2) 또는 true verb 형 없이 adj 항목이 있음
            if cat == "동사":
                if (has_part and not has_true_verb) and (has_adj or has_noun):
                    suspected = True
                elif has_adj and not has_true_verb and not has_part:
                    suspected = True
        break  # 첫 번째 유효 lemma만 사용

    _c2pos_cache[word] = (cat, suspected)
    return cat, suspected


def measure_dual(text: str) -> dict:
    """한 번 순회로 C1+ 비율(기존)과 C2-동사+부사 비율(신규)을 동시 계산."""
    seen: set[str] = set()
    total = c1plus = c2_verb = c2_adv = 0
    c2_verb_words: list[tuple[str, bool]] = []
    c2_adv_words:  list[str] = []

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

            lv = get_cefr(w)
            if lv is None:
                continue
            total += 1
            if lv in ("C1", "C2"):
                c1plus += 1
            if lv == "C2":
                cat, susp = _c2_pos(w)
                if cat == "동사":
                    c2_verb += 1
                    c2_verb_words.append((w, susp))
                elif cat == "부사":
                    c2_adv += 1
                    c2_adv_words.append(w)

    c1pct   = round(c1plus / total * 100, 2) if total else 0.0
    c2va_pct = round((c2_verb + c2_adv) / total * 100, 2) if total else 0.0
    return {
        "total": total, "c1plus": c1plus,
        "c2_verb": c2_verb, "c2_adv": c2_adv,
        "c2_verb_words": c2_verb_words, "c2_adv_words": c2_adv_words,
        "c1pct": c1pct, "c2va_pct": c2va_pct,
    }


# ── 데이터 로딩 ───────────────────────────────────────────────────────────────
EXCLUDE_SECTIONS = {
    "Photo News","Briefs","Star Brief","News in Brief","Cartoon",
    "Did You Know","Did You Know?","Debating","Cover","Q & A",
    "NE You","My Journal","Book Review","Stories","Story",
    "Readings for Junior","VoA Broadcast News","Think About It","My Diary","Debate",
}
TARGET_ISS = {"767","978","1045","980","1022"}
TARGET_LABEL = {
    "767":  "CCTV 767호[2020]",
    "978":  "T-rex 978호[2024]",
    "1045": "로봇 1045호[2025]",
    "980":  "매미 980호[2024]",
    "1022": "비행 1022호[2025]",
}
_YEAR_RE = re.compile(r'\b(20\d{2})\b')

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]

def _ci(pat: str):
    return next((i for i,h in enumerate(hdr) if pat in h or pat.lower() in h.lower()), None)
lv_col, tx_col, sc_col, dt_col, iss_col = _ci("레벨"), _ci("본문"), _ci("섹션"), _ci("날짜"), _ci("호수")

def gc(row, col):
    if col is None or len(row) <= col or row[col] is None: return ""
    return str(row[col]).strip()

# ── 한 번 순회 — 2024+ 분포용 + 타겟 5건 별도 수집 ─────────────────────────────
sec_data: dict[str, list[tuple[float,float]]] = collections.defaultdict(list)
target_arts: dict[str, tuple[str,str]] = {}   # iss → (tx, dt)
total_processed = 0

print("분석 중...", end="", flush=True)

for row in rows[1:]:
    if not row: continue
    lv_raw = gc(row, lv_col)
    if re.sub(r'[^0-9]', '', lv_raw) != "2": continue
    sc  = gc(row, sc_col)
    tx  = gc(row, tx_col)
    dt  = gc(row, dt_col)
    iss = gc(row, iss_col)
    if not tx or len(tx) < 30: continue
    if sc in EXCLUDE_SECTIONS: continue
    cls = classify(tx, "TIMES_L2")
    if cls.skip_cefr: continue

    # 타겟 기사 수집 (연도 무관)
    if iss in TARGET_ISS and iss not in target_arts:
        if iss == "767":
            if "CCTV" in tx or "surveillance" in tx.lower():
                target_arts[iss] = (tx, dt)
        else:
            target_arts[iss] = (tx, dt)

    # 2024+ 섹션 분포
    ym = _YEAR_RE.search(dt)
    yr = int(ym.group()) if ym else None
    if yr is not None and yr < 2024: continue
    m = measure_dual(tx)
    sec_data[sc].append((m["c1pct"], m["c2va_pct"]))
    total_processed += 1
    print(".", end="", flush=True)

print(f" 완료 ({total_processed}건)\n")


# ── 섹션별 분포 출력 ─────────────────────────────────────────────────────────
def pct(xs, p):
    if not xs: return float("nan")
    s = sorted(xs)
    return s[min(int(len(s) * p / 100), len(s)-1)]

SEC_ORDER = [
    "Headlines News","World","Key Issue","Science",
    "Read and Learn","Lifestyle","Sports & Entertainment",
]
extras = [s for s in sec_data if s not in SEC_ORDER]
all_secs = SEC_ORDER + sorted(extras)

print("=" * 90)
print("섹션별 분포  —  C2_동사부사 비율 (신규) vs C1+ 비율 (기존)  |  TIMES_L2 2024+ dedup")
print("=" * 90)
print(f"  {'섹션':<26}  {'n':>4}  "
      f"{'C2VA-p50':>9}  {'p75':>6}  {'p90':>6}  {'p95':>6}  ||  "
      f"{'C1+-p50':>8}  {'p75':>6}  {'p90':>6}  {'p95':>6}")
print("  " + "-"*88)

for sec in all_secs:
    pairs = sec_data.get(sec, [])
    if not pairs: continue
    va  = [x[1] for x in pairs]
    c1  = [x[0] for x in pairs]
    print(f"  {sec:<26}  {len(va):>4}  "
          f"{pct(va,50):>8.2f}%  {pct(va,75):>5.2f}%  {pct(va,90):>5.2f}%  {pct(va,95):>5.2f}%  ||  "
          f"{pct(c1,50):>7.1f}%  {pct(c1,75):>5.1f}%  {pct(c1,90):>5.1f}%  {pct(c1,95):>5.1f}%")


# ── 5개 타겟 기사 상세 비교 ───────────────────────────────────────────────────
ORDER = ["767","978","1045","980","1022"]

print("\n\n" + "=" * 90)
print("타겟 5건 — 새 지표(C2 동사+부사%) vs 기존 지표(C1+%) 나란히")
print("=" * 90)
print(f"  {'기사':<22}  {'total':>6}  {'C2_V':>5}  {'C2_A':>5}  "
      f"{'C2VA%':>7}  {'C1+%':>6}  {'비율비(VA/C1+)':>12}")
print("  " + "-"*70)

target_details: dict[str, dict] = {}
for iss in ORDER:
    lbl = TARGET_LABEL.get(iss, iss)
    if iss not in target_arts:
        print(f"  {lbl:<22}  기사 없음")
        continue
    tx, dt = target_arts[iss]
    m = measure_dual(tx)
    target_details[iss] = m
    ratio_of_ratio = round(m["c2va_pct"] / m["c1pct"] * 100, 0) if m["c1pct"] else 0
    print(f"  {lbl:<22}  {m['total']:>6}  {m['c2_verb']:>5}  {m['c2_adv']:>5}  "
          f"{m['c2va_pct']:>6.2f}%  {m['c1pct']:>5.1f}%  {ratio_of_ratio:>10.0f}%")


# ── 타겟 5건 C2 동사·부사 상세 + 오분류 의심 집계 ────────────────────────────
print("\n\n" + "=" * 90)
print("타겟 5건 — C2 동사·부사 단어 목록 + 오분류 의심 체크")
print("오분류 의심(★): 분사형(VBG/VBN)만으로 동사 판정됐고 JJ/NN 항목도 존재")
print("=" * 90)

total_suspect = 0
total_verb = 0

for iss in ORDER:
    lbl = TARGET_LABEL.get(iss, iss)
    if iss not in target_details:
        continue
    m = target_details[iss]
    vws = m["c2_verb_words"]
    aws = m["c2_adv_words"]

    v_clean   = [(w,s) for w,s in vws if not s]
    v_suspect = [(w,s) for w,s in vws if s]
    total_verb    += len(vws)
    total_suspect += len(v_suspect)

    print(f"\n▌ {lbl}  C2동사={m['c2_verb']}개 (의심={len(v_suspect)})  C2부사={m['c2_adv']}개")
    if aws:
        print(f"  [C2 부사] {', '.join(aws)}")
    if v_clean:
        print(f"  [C2 동사] {', '.join(w for w,_ in v_clean)}")
    if v_suspect:
        print(f"  [★오분류의심] {', '.join(w for w,_ in v_suspect)}")

print(f"\n전체 5건 C2 동사 총 {total_verb}개 중 오분류 의심: {total_suspect}개 "
      f"({round(total_suspect/total_verb*100) if total_verb else 0}%)")

# ── 전체 2024+ 분포 기준 5건 위치 ─────────────────────────────────────────────
all_va_2024 = [x[1] for pairs in sec_data.values() for x in pairs]
all_c1_2024 = [x[0] for pairs in sec_data.values() for x in pairs]
n_all = len(all_va_2024)

print("\n\n" + "=" * 90)
print(f"타겟 5건 위치 — 전체 2024+ 분포 내 백분위 (n={n_all})")
print("=" * 90)
print(f"  {'기사':<22}  {'C2VA%':>7}  {'VA-pctile':>10}  {'C1+%':>6}  {'C1-pctile':>10}")
print("  " + "-"*62)
for iss in ORDER:
    lbl = TARGET_LABEL.get(iss, iss)
    if iss not in target_details: continue
    m = target_details[iss]
    va_p  = round(sum(1 for x in all_va_2024 if x <= m["c2va_pct"]) / n_all * 100, 1)
    c1_p  = round(sum(1 for x in all_c1_2024 if x <= m["c1pct"])    / n_all * 100, 1)
    print(f"  {lbl:<22}  {m['c2va_pct']:>6.2f}%  {va_p:>9.1f}%  {m['c1pct']:>5.1f}%  {c1_p:>9.1f}%")
