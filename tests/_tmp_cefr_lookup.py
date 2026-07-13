"""Words-CEFR-Dataset에서 guidelines NOT/USE/domain 단어 레벨 조회."""
import sys, io, csv, os, urllib.request, zipfile, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 1. cefrpy 모듈 시도 ────────────────────────────────────────────────────
try:
    import cefrpy
    USE_CEFRPY = True
    print("cefrpy 모듈 사용")
except ImportError:
    USE_CEFRPY = False
    print("cefrpy 없음 → CSV 직접 다운로드")

# ── 2. CSV 다운로드 (cefrpy 없을 때) ──────────────────────────────────────
CACHE_DIR  = r"C:\Users\jp\work\news-pipeline5\tests\_cefr_data"
CSV_PATH   = os.path.join(CACHE_DIR, "words_cefr.csv")
# GitHub raw URL - Maximax67/Words-CEFR-Dataset
RAW_URL    = "https://raw.githubusercontent.com/Maximax67/Words-CEFR-Dataset/main/data/words.csv"
RAW_URL_2  = "https://raw.githubusercontent.com/Maximax67/Words-CEFR-Dataset/main/words.csv"
CEFRJ_URL  = "https://raw.githubusercontent.com/openlanguageprofiles/olp-en-cefrj/master/cefrj-vocabulary-profile-1.5.csv"

os.makedirs(CACHE_DIR, exist_ok=True)

def try_download(url, path, label):
    try:
        print(f"  다운로드 시도: {url}")
        urllib.request.urlretrieve(url, path)
        size = os.path.getsize(path)
        print(f"  → {size:,} bytes 저장")
        return True
    except Exception as e:
        print(f"  → 실패: {e}")
        return False

cefr_map = {}   # word → level

if USE_CEFRPY:
    analyzer = cefrpy.CEFRAnalyzer()
    def get_level(word):
        try:
            lv = analyzer.get_level(word)
            return lv if lv else None
        except Exception:
            return None
else:
    # Words-CEFR-Dataset CSV 로드 시도
    if not os.path.exists(CSV_PATH) or os.path.getsize(CSV_PATH) < 1000:
        ok = try_download(RAW_URL, CSV_PATH, "words.csv (path1)")
        if not ok:
            ok = try_download(RAW_URL_2, CSV_PATH, "words.csv (path2)")
        if not ok:
            # CEFR-J 폴백
            print("  Words-CEFR-Dataset 실패 → CEFR-J 폴백")
            try_download(CEFRJ_URL, CSV_PATH, "CEFR-J CSV")

    if os.path.exists(CSV_PATH) and os.path.getsize(CSV_PATH) > 1000:
        with open(CSV_PATH, encoding="utf-8", errors="replace") as f:
            first = f.readline()
        print(f"\nCSV 헤더: {first.strip()}")
        # 컬럼 자동 감지
        headers = [h.strip().lower() for h in first.split(",")]
        print(f"컬럼 목록: {headers}")
        word_col  = next((i for i,h in enumerate(headers) if h in ("word","headword","lemma","token")), 0)
        level_col = next((i for i,h in enumerate(headers) if "cefr" in h or h == "level"), None)
        if level_col is None:
            level_col = 1
        print(f"사용 컬럼: word={word_col}, level={level_col}\n")
        with open(CSV_PATH, encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            next(reader)  # header
            for row in reader:
                if len(row) <= max(word_col, level_col): continue
                w = row[word_col].strip().lower()
                lv = row[level_col].strip().upper()
                if w and lv:
                    cefr_map[w] = lv
        print(f"로드 완료: {len(cefr_map):,}개 단어")
    else:
        print("CSV 로드 실패")

    def get_level(word):
        w = word.lower().strip()
        if w in cefr_map:
            return cefr_map[w]
        # 기본형 시도 (간단한 stem)
        for stem in [w.rstrip("s"), w.rstrip("ing"), w.rstrip("ed"),
                     w.rstrip("tion").rstrip("iza"), w.rstrip("ers").rstrip("er")]:
            if stem != w and stem in cefr_map:
                return f"{cefr_map[stem]}~"
        return None

# ── 3. 조회 대상 ──────────────────────────────────────────────────────────
NOT_L1 = [
    "proponents", "deterring", "incorporating",
    "measurable", "margins", "advocates",
]
NOT_L23 = [
    "proliferation", "contend", "criminologists",
    "conducted",
]
USE_L1 = [
    "supporters", "stopping", "using",
    "privacy", "groups",
]
USE_L23 = [
    "say", "keep", "pace", "installed",
]
DOMAIN_OK = [
    "GDP", "legislation", "surveillance",
]

def lookup_table(words, section_label):
    print(f"\n{'─'*60}")
    print(f"{section_label}")
    print(f"{'─'*60}")
    print(f"{'단어':<28} {'데이터셋 레벨':>14}  비고")
    print(f"{'─'*60}")
    missing = 0
    for w in words:
        lv = get_level(w)
        if lv is None:
            lv_str = "(미수록)"
            missing += 1
        else:
            lv_str = lv
        print(f"  {w:<26} {lv_str:>14}")
    print(f"  미수록: {missing}/{len(words)}건")

lookup_table(NOT_L1,    "NOT 단어 — L1 (B1 기준 금지, 기대: C1+)")
lookup_table(NOT_L23,   "NOT 단어 — L2/L3 (B2 기준 금지, 기대: C1+)")
lookup_table(USE_L1,    "USE 대체어 — L1 (기대: B1 이하)")
lookup_table(USE_L23,   "USE 대체어 — L2/L3 (기대: B2 이하)")
lookup_table(DOMAIN_OK, "Domain terms — B2에서 OK (C1 나오면 보정 필요)")
