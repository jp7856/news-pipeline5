"""대화체 감지 필터 검증 — 알려진 대화체 기사와 일반 기사 false positive 확인.

판정 기준: "짧은 단어 + 콜론 + 공백"으로 시작하는 줄이 3번 이상 → 대화체.
"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import openpyxl

XLSX_PATH = r"C:\Users\jp\Desktop\기사\articles.xlsx"
EXCLUDE_SECTIONS = {
    "Photo News", "Briefs", "Star Brief", "News in Brief",
    "Cartoon", "Did You Know", "Did You Know?", "Debating", "Cover", "Q & A",
    "NE You",
}
MIN_WC = 100

# ── 대화체 감지 함수 ───────────────────────────────────────────────────────
# "Kelly: I admire..." 형태 — 줄 시작에 이름+콜론, 뒤 내용이 5단어 이상
# 5단어 미만 제외 이유: "Height: 185 cm" 같은 프로필 필드 오매칭 방지
_DIALOGUE_PREFIX = re.compile(
    r"^\s*([A-Z][a-z]{1,19}(?:\s[A-Z][a-z]{1,19})?):\s+(.*)"
)
DIALOGUE_THRESHOLD = 3


def _is_dialogue_line(line: str) -> bool:
    m = _DIALOGUE_PREFIX.match(line)
    if not m:
        return False
    content_words = len(re.findall(r"\w+", m.group(2)))
    return content_words >= 5  # 실제 발화문 vs 프로필 필드 구분


def is_dialogue(text: str) -> tuple[bool, int]:
    """(대화체 여부, 감지된 대화 줄 수) 반환."""
    count = sum(1 for line in text.splitlines() if _is_dialogue_line(line))
    return count >= DIALOGUE_THRESHOLD, count


# ── TIMES_L1 기사 로드 ────────────────────────────────────────────────────
wb   = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws   = wb["TIMES"]
rows = list(ws.iter_rows(values_only=True))
hdr  = [str(c).strip() if c else "" for c in rows[0]]
lv_col  = next(i for i,h in enumerate(hdr) if "레벨" in h or "level" in h.lower())
tx_col  = next(i for i,h in enumerate(hdr) if "본문" in h or "text" in h.lower())
sec_col = next(i for i,h in enumerate(hdr) if "섹션" in h or "section" in h.lower())
ttl_col = next((i for i,h in enumerate(hdr) if "제목" in h or "title" in h.lower()), None)

articles = []
for row in rows[1:]:
    if not row or len(row) <= max(lv_col, tx_col): continue
    lv  = str(row[lv_col]).strip()  if row[lv_col]  else ""
    txt = str(row[tx_col]).strip()  if row[tx_col]  else ""
    sec = str(row[sec_col]).strip() if row[sec_col] else ""
    ttl = str(row[ttl_col]).strip() if (ttl_col and row[ttl_col]) else ""
    if lv != "LEVEL 1": continue
    if sec in EXCLUDE_SECTIONS: continue
    wc = len(re.findall(r"[A-Za-z']+", txt))
    if wc < MIN_WC: continue
    articles.append((sec, ttl, wc, txt))

total = len(articles)
flagged = [(sec, ttl, wc, txt) for sec, ttl, wc, txt in articles if is_dialogue(txt)[0]]

# ── 알려진 대화체([6][10]) 검출 확인 ─────────────────────────────────────
KNOWN_DIALOGUES = [
    "Kelly: I really admire your jacket",   # 샘플 [6]
    "Katie: What do you feel like having",  # 샘플 [10]
]

print("[ 알려진 대화체 감지 확인 ]")
print(f"{'─'*60}")
for snippet in KNOWN_DIALOGUES:
    hit = next((t for _,_,_,t in articles if snippet in t), None)
    if hit is None:
        print(f"  !! 못 찾음: {snippet[:50]}")
        continue
    detected, count = is_dialogue(hit)
    mark = "✓ 감지됨" if detected else "✗ 미감지"
    print(f"  {mark}  대화줄={count}개  미리보기: {hit[:70].replace(chr(10),' ')}...")

# ── 전체 대화체 비율 ──────────────────────────────────────────────────────
print(f"\n[ 전체 TIMES_L1 (섹션·단신 필터 후) ]")
print(f"  총 {total}건 중 대화체 판정: {len(flagged)}건 ({len(flagged)/total*100:.1f}%)")

# 섹션별 대화체 분포
sec_counts: dict[str, int] = {}
sec_totals: dict[str, int] = {}
for sec, ttl, wc, txt in articles:
    sec_totals[sec] = sec_totals.get(sec, 0) + 1
    if is_dialogue(txt)[0]:
        sec_counts[sec] = sec_counts.get(sec, 0) + 1

print(f"\n[ 섹션별 대화체 건수 (1건 이상인 섹션만) ]")
print(f"{'섹션':<30} {'대화체':>6} {'전체':>6} {'비율':>6}")
print(f"{'─'*50}")
for sec in sorted(sec_counts, key=lambda s: -sec_counts[s]):
    n = sec_counts[sec]
    t = sec_totals[sec]
    print(f"  {sec:<28} {n:>6}건 {t:>5}건 {n/t*100:>5.0f}%")

# ── false positive 확인: 일반 기사 10건 샘플 (대화체 0건인지) ────────────
normal = [(sec, ttl, wc, txt) for sec, ttl, wc, txt in articles if not is_dialogue(txt)[0]]
print(f"\n[ False positive 점검 — 대화체 판정된 기사 중 실제 비대화체인 것 ]")
print(f"{'─'*60}")
# 대화줄이 1~2개 있지만 3개 미만이라 통과된 케이스 확인
borderline = [
    (sec, ttl, wc, txt) for sec, ttl, wc, txt in articles
    if is_dialogue(txt)[1] in (1, 2)
]
print(f"  대화줄 1~2개 (경계선): {len(borderline)}건 — 아래는 무작위 5건")
import random; random.seed(42)
for sec, ttl, wc, txt in random.sample(borderline, min(5, len(borderline))):
    _, cnt = is_dialogue(txt)
    print(f"  [{sec}] 대화줄={cnt}  {txt[:100].replace(chr(10),' ')}...")

# 대화체로 잘못 판정됐을 가능성: flagged 중 비대화체처럼 보이는 것 5건
print(f"\n  대화체로 판정된 {len(flagged)}건 중 샘플 5건 (false positive 육안 확인)")
for sec, ttl, wc, txt in flagged[:5]:
    _, cnt = is_dialogue(txt)
    print(f"\n  [{sec}] 대화줄={cnt}  wc={wc}")
    print(f"  {txt[:200].replace(chr(10),' ')}...")
