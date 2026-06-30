"""
dedup 메커니즘 분석 + Science 상위 4건 + CCTV 두 지문 재확인.
"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl
from agents.sub_agents.vocab_checker import (
    measure, get_cefr, DOMAIN_TERMS, _SENT_SPLIT, _TOKEN
)
from agents.sub_agents.article_classifier import classify

XLSX_PATH  = r"C:\Users\jp\Desktop\기사\articles.xlsx"
_YEAR_RE   = re.compile(r'\b(20\d{2})\b')
_CCTV_767  = re.compile(r'767')

EXCLUDE_SECTIONS = {
    "Photo News", "Briefs", "Star Brief", "News in Brief",
    "Cartoon", "Did You Know", "Did You Know?",
    "Debating", "Cover", "Q & A",
    "NE You", "My Journal", "Book Review",
    "Stories", "Story", "Readings for Junior",
    "VoA Broadcast News", "Think About It", "My Diary", "Debate",
}

def gc(row, col):
    if col is None or len(row) <= col or row[col] is None:
        return ""
    return str(row[col]).strip()

# ── 1. dedup 메커니즘 분해 함수 ───────────────────────────────────────────────
def decompose(text: str) -> dict:
    """토큰 기준과 dedup 기준 분모/분자를 나란히 계산해 반환."""
    # --- 토큰 기준 ---
    tok_total = tok_c1 = tok_c2 = 0
    # --- dedup 기준 ---
    seen: set[str] = set()
    dup_total = dup_c1 = dup_c2 = 0
    # --- 반복 상위 단어 추적 ---
    token_freq: dict[str, int] = {}
    cefr_freq:  dict[str, tuple] = {}   # w -> (lv, count)

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
            lv = get_cefr(w)
            if lv is None:
                continue

            token_freq[w] = token_freq.get(w, 0) + 1

            # 토큰 기준: 매 등장마다 집계
            tok_total += 1
            if lv == "C1": tok_c1 += 1
            elif lv == "C2": tok_c2 += 1

            # dedup 기준: 첫 등장만 집계
            if w not in seen:
                seen.add(w)
                dup_total += 1
                if lv == "C1": dup_c1 += 1
                elif lv == "C2": dup_c2 += 1

            if lv in ("C1", "C2"):
                prev_lv, prev_cnt = cefr_freq.get(w, (lv, 0))
                cefr_freq[w] = (lv, prev_cnt + 1)

    tok_ratio = (tok_c1 + tok_c2) / tok_total if tok_total else 0
    dup_ratio = (dup_c1 + dup_c2) / dup_total if dup_total else 0

    # 가장 많이 반복된 B1/B2 단어 (분모 차이 설명용)
    b12_repeats = sorted(
        [(w, cnt) for w, cnt in token_freq.items()
         if cnt > 1 and get_cefr(w) in ("A1","A2","B1","B2")],
        key=lambda x: -x[1]
    )[:8]

    # C1/C2 단어 목록 (반복 포함)
    c_words = sorted(cefr_freq.items(), key=lambda x: -x[1][1])

    return {
        "tok_total": tok_total, "tok_c1": tok_c1, "tok_c2": tok_c2,
        "tok_ratio": tok_ratio,
        "dup_total": dup_total, "dup_c1": dup_c1, "dup_c2": dup_c2,
        "dup_ratio": dup_ratio,
        "b12_repeats": b12_repeats,
        "c_words": c_words,
        "tok_shrank": tok_total - dup_total,   # 분모 감소량
    }

# ── 데이터 로딩 ───────────────────────────────────────────────────────────────
wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]

lv_col  = next((i for i,h in enumerate(hdr) if "레벨"  in h or "level"   in h.lower()), None)
tx_col  = next((i for i,h in enumerate(hdr) if "본문"  in h or "text"    in h.lower()), None)
sc_col  = next((i for i,h in enumerate(hdr) if "섹션"  in h or "section" in h.lower()), None)
dt_col  = next((i for i,h in enumerate(hdr) if "날짜"  in h or "date"    in h.lower()), None)
iss_col = next((i for i,h in enumerate(hdr) if "호수"  in h or "issue"   in h.lower()), None)

# ── 2. CCTV 두 지문 수집 ─────────────────────────────────────────────────────
cctv_re = re.compile(r'\bCCTV\b')
# iss 컬럼은 숫자만("767"), dt 컬럼은 "[767호] 2020.03.02"
target_iss_nums = {"767": "767호", "1043": "1043호"}
cctv_articles = {}   # "767호" / "1043호" → (tx, sc, dt, iss)

for row in rows[1:]:
    if not row: continue
    lv_raw = gc(row, lv_col)
    if re.sub(r'[^0-9]', '', lv_raw) != "2": continue
    iss = gc(row, iss_col)
    tx  = gc(row, tx_col)
    sc  = gc(row, sc_col)
    dt  = gc(row, dt_col)
    # iss == "767" 또는 "1043"이면서 CCTV 포함
    if iss not in target_iss_nums: continue
    label = target_iss_nums[iss]
    if not cctv_re.search(tx): continue
    if sc in EXCLUDE_SECTIONS: continue
    cls = classify(tx, "TIMES_L2")
    if cls.skip_cefr: continue
    if label not in cctv_articles:
        cctv_articles[label] = (tx, sc, dt, iss)

# ── 3. Science 2024+ 기사 수집 (CCTV 범위 초과 4건 찾기) ──────────────────────
print("Science 섹션 분석 중...", end="", flush=True)
science_results = []   # (c1pct, c2pct, iss, dt, tx[:200])

for row in rows[1:]:
    if not row: continue
    lv_raw = gc(row, lv_col)
    if re.sub(r'[^0-9]', '', lv_raw) != "2": continue
    sc  = gc(row, sc_col)
    tx  = gc(row, tx_col)
    dt  = gc(row, dt_col)
    iss = gc(row, iss_col)
    if sc != "Science": continue
    if sc in EXCLUDE_SECTIONS: continue
    ym = _YEAR_RE.search(dt)
    yr = int(ym.group()) if ym else None
    if yr is not None and yr < 2024: continue
    if not tx or len(tx) < 30: continue
    cls = classify(tx, "TIMES_L2")
    if cls.skip_cefr: continue
    res = measure(tx, dedup_types=True)
    denom = res.total_words
    c2pct = round(res.c2_count / denom * 100, 1) if denom else 0.0
    science_results.append((res.c1plus_pct, c2pct, iss, dt, tx.strip()[:200]))
    print(".", end="", flush=True)

print(" 완료\n")

# ════════════════════════════════════════════════════════════════════
# 출력 1 — dedup 메커니즘 설명 (CCTV 767호 기준)
# ════════════════════════════════════════════════════════════════════
print("=" * 70)
print("1. dedup 메커니즘 — CCTV 767호 수치 분해")
print("=" * 70)

if "767호" in cctv_articles:
    tx767, sc767, dt767, iss767 = cctv_articles["767호"]
    d = decompose(tx767)

    print(f"\n  호수/날짜: {iss767} {dt767}  섹션: {sc767}\n")
    print("  ┌─ 토큰 기준 (dedup=False) ──────────────────────────────┐")
    print(f"  │  분모(total) = {d['tok_total']}개  분자(C1+C2) = {d['tok_c1']+d['tok_c2']}개")
    print(f"  │  비율 = {d['tok_c1']+d['tok_c2']} / {d['tok_total']} = {d['tok_ratio']*100:.1f}%")
    print("  └────────────────────────────────────────────────────────┘")
    print("  ┌─ dedup 기준 (dedup=True) ──────────────────────────────┐")
    print(f"  │  분모(unique total) = {d['dup_total']}개  분자(unique C1+C2) = {d['dup_c1']+d['dup_c2']}개")
    print(f"  │  비율 = {d['dup_c1']+d['dup_c2']} / {d['dup_total']} = {d['dup_ratio']*100:.1f}%")
    print("  └────────────────────────────────────────────────────────┘")
    print(f"\n  분모 감소: {d['tok_total']} → {d['dup_total']}  (−{d['tok_shrank']}개 중복 제거)")
    print(f"  C1+C2 감소: {d['tok_c1']+d['tok_c2']} → {d['dup_c1']+d['dup_c2']}  "
          f"(C1: {d['tok_c1']}→{d['dup_c1']}, C2: {d['tok_c2']}→{d['dup_c2']})")

    shrink_pct_denom = d['tok_shrank'] / d['tok_total'] * 100 if d['tok_total'] else 0
    c_shrink = (d['tok_c1']+d['tok_c2']) - (d['dup_c1']+d['dup_c2'])
    shrink_pct_num = c_shrink / (d['tok_c1']+d['tok_c2']) * 100 if (d['tok_c1']+d['tok_c2']) else 0
    print(f"\n  분모 감소율: {shrink_pct_denom:.1f}%  분자 감소율: {shrink_pct_num:.1f}%")
    print("  → 분모가 분자보다 더 많이 줄어 비율이 상승함")
    print()
    print("  B1/B2 반복 상위 단어 (분모 감소 주원인):")
    for w, cnt in d['b12_repeats']:
        lv = get_cefr(w)
        print(f"    '{w}' {cnt}회 ({lv})")
    print()
    print("  C1/C2 단어 목록:")
    for w, (lv, cnt) in d['c_words']:
        print(f"    '{w}' {cnt}회 → {lv}")
else:
    print("  767호 CCTV 기사를 찾지 못함 — 목록:", list(cctv_articles.keys()))

# ════════════════════════════════════════════════════════════════════
# 출력 2 — Science 상위 4건 (7.9% 초과)
# ════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("2. Science 섹션 C1+ 상위 4건 (dedup 7.9% 초과)")
print("=" * 70)

top4 = sorted([r for r in science_results if r[0] > 7.9], key=lambda x: -x[0])
if not top4:
    top4 = sorted(science_results, key=lambda x: -x[0])[:4]
    print("  (7.9% 초과 없음 — 상위 4건 표시)")

for i, (c1pct, c2pct, iss, dt, prev) in enumerate(top4, 1):
    print(f"\n  #{i}  C1+={c1pct:.1f}%  C2={c2pct:.1f}%  섹션=Science  {iss} {dt}")
    print(f"  {prev.replace(chr(10), ' ')}")

# ════════════════════════════════════════════════════════════════════
# 출력 3 — CCTV 두 지문 dedup/토큰 나란히
# ════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("3. CCTV 두 지문 — 토큰 vs dedup 나란히")
print("=" * 70)

for key in ["767호", "1043호"]:
    if key not in cctv_articles:
        print(f"\n  {key}: 데이터 없음")
        continue
    tx, sc, dt, iss = cctv_articles[key]
    r_tok = measure(tx, dedup_types=False)
    r_dup = measure(tx, dedup_types=True)
    denom_t = r_tok.total_words
    denom_d = r_dup.total_words
    c2_tok = round(r_tok.c2_count / denom_t * 100, 1) if denom_t else 0
    c2_dup = round(r_dup.c2_count / denom_d * 100, 1) if denom_d else 0
    print(f"\n  {iss} {dt}  섹션: {sc}")
    print(f"  토큰 기준:  C1+={r_tok.c1plus_pct:.1f}%  C2={c2_tok:.1f}%  "
          f"(분모={denom_t}, C1+C2={r_tok.c1_count+r_tok.c2_count})")
    print(f"  dedup 기준: C1+={r_dup.c1plus_pct:.1f}%  C2={c2_dup:.1f}%  "
          f"(분모={denom_d}, C1+C2={r_dup.c1_count+r_dup.c2_count})")
    print(f"  본문: {tx.strip()[:120].replace(chr(10), ' ')}")
