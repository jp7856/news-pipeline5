"""
STRONG 4건 본문 앞 200자 + NOT 단어 출현 위치
CCTV 분석어 후보 6개의 코퍼스 내 섹션·맥락 분포
판단 없음 — 원문 그대로 출력.
"""
import sys, io, re, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import openpyxl
from agents.sub_agents.vocab_checker import NOT_WORDS, _NOT_PATTERNS
from agents.sub_agents.article_classifier import classify

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"
EXCLUDE_SECTIONS = {
    "Photo News","Briefs","Star Brief","News in Brief","Cartoon",
    "Did You Know","Did You Know?","Debating","Cover","Q & A",
    "NE You","My Journal","Book Review","Stories","Story",
    "Readings for Junior","VoA Broadcast News","Think About It","My Diary","Debate",
}

wb  = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws  = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
def ci(p): return next((i for i,h in enumerate(hdr) if p in h or p.lower() in h.lower()), None)
lv_col = ci("레벨"); tx_col = ci("본문"); sc_col = ci("섹션")
dt_col = ci("날짜"); iss_col = ci("호수"); ti_col = ci("제목")
def gc(r,c):
    if c is None or len(r)<=c or r[c] is None: return ""
    return str(r[c]).strip()

SEP  = "=" * 72
SEP2 = "-" * 60

# ── STRONG 4건 대상 ──────────────────────────────────────────────────────────
STRONG_TARGETS = {
    ("960", "Key Issue"),
    ("973", "Key Issue"),
    ("994", "Key Issue"),
    ("983", "Key Issue"),
}

# ── CCTV 분석어 후보 ──────────────────────────────────────────────────────────
CCTV_WORDS = ["loitering", "trespassing", "sift", "pinpoint", "preemptively", "misdemeanors"]
_CCTV_PATS = {
    w: re.compile(r"\b" + re.escape(w) + r"\b", re.IGNORECASE) for w in CCTV_WORDS
}

# ── 코퍼스 1회 순회 ────────────────────────────────────────────────────────────
strong_arts:  list[dict] = []
# word → list of (iss, section, context_sentence)
cctv_hits: dict[str, list[tuple]] = {w: [] for w in CCTV_WORDS}

_YR = re.compile(r"\b(20\d{2})\b")

for row in rows[1:]:
    if not row: continue
    if re.sub(r"[^0-9]","", gc(row, lv_col)) != "2": continue
    sc  = gc(row, sc_col)
    tx  = gc(row, tx_col)
    iss = gc(row, iss_col)
    dt  = gc(row, dt_col)
    ti  = gc(row, ti_col) if ti_col is not None else ""
    if not tx or len(tx) < 30: continue

    # STRONG 4건 수집 (섹션 필터 없이 — Key Issue는 EXCLUDE 아님)
    if (iss, sc) in STRONG_TARGETS:
        not_hits = {w: cnt for w,p in _NOT_PATTERNS.items() if (cnt:=len(p.findall(tx)))>0}
        # NOT 단어 출현 주변 문장 추출
        not_contexts = {}
        for w, p in _NOT_PATTERNS.items():
            sents = []
            for sent in re.split(r"(?<=[.!?])\s+", tx):
                if p.search(sent):
                    sents.append(sent.strip())
            if sents:
                not_contexts[w] = sents[:3]  # 최대 3문장
        strong_arts.append({
            "iss": iss, "sc": sc, "dt": dt, "ti": ti,
            "preview": tx[:200],
            "not_hits": not_hits,
            "not_contexts": not_contexts,
        })

    # CCTV 분석어 출현 수집
    if sc in EXCLUDE_SECTIONS: continue
    cls = classify(tx, "TIMES_L2")
    if cls.skip_cefr: continue
    for w, pat in _CCTV_PATS.items():
        if not pat.search(tx): continue
        # 출현 문장 1개
        ctx = ""
        for sent in re.split(r"(?<=[.!?])\s+", tx):
            if pat.search(sent):
                ctx = sent.strip()[:120]
                break
        cctv_hits[w].append((iss, sc, dt, ctx))


# ── 출력 1: STRONG 4건 ────────────────────────────────────────────────────────
print(SEP)
print("STRONG 4건 — 본문 앞 200자 + NOT 단어 출현 문장")
print(SEP)

for art in strong_arts:
    print(f"\n[{art['iss']}호 {art['sc']}]  {art['dt']}")
    if art["ti"] and "전체메뉴" not in art["ti"]:
        print(f"제목: {art['ti'][:80]}")
    print(f"본문 앞 200자:\n  {art['preview']}")
    print(f"NOT 단어 출현: {art['not_hits']}")
    for w, sents in art["not_contexts"].items():
        for s in sents:
            print(f"  [{w}] {s[:140]}")

# ── 출력 2: CCTV 분석어 코퍼스 분포 ─────────────────────────────────────────────
print(f"\n{SEP}")
print("CCTV 분석어 후보 — TIMES_L2 코퍼스 출현 섹션·맥락")
print(f"(판단 없음 — 어느 토픽에서 나왔는지 보여줌)")
print(SEP)

for w in CCTV_WORDS:
    hits = cctv_hits[w]
    if not hits:
        print(f"\n  {w}: 코퍼스 내 출현 없음")
        continue

    # 섹션별 건수
    sec_count = collections.Counter(sc for _,sc,_,_ in hits)
    print(f"\n  [{w}]  총 {len(hits)}건  섹션분포: {dict(sec_count.most_common(6))}")
    # 출현 문장 최대 8건 (섹션 다양하게)
    shown_secs: set[str] = set()
    count = 0
    for iss, sc, dt, ctx in sorted(hits, key=lambda x: x[1]):  # 섹션순
        if count >= 8: break
        marker = "  " if sc in shown_secs else "→ "
        shown_secs.add(sc)
        print(f"    {marker}{iss} [{sc}] {dt}")
        print(f"      {ctx}")
        count += 1
