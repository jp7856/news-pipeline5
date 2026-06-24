"""basic.xlsx — JUNIOR LEVEL 2, JUNIOR M LEVEL 1 실측 FK 측정."""
import sys, io, re, statistics
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import openpyxl

XLSX_PATH = r"C:\Users\jp\Desktop\basic.xlsx"

try:
    import textstat
    _HAS_TEXTSTAT = True
except ImportError:
    _HAS_TEXTSTAT = False


def _split_sentences(text):
    return [p for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p.strip()]

def _count_clauses(sentence):
    m = re.findall(r"\b(and|but|or|because|although|though|which|who|that|when|while|if|since)\b",
                   sentence, re.IGNORECASE)
    return 1 + len(m) + sentence.count(";") + sentence.count("—")

def _syllables(word):
    w = word.lower()
    g = re.findall(r"[aeiouy]+", w)
    n = len(g)
    if w.endswith("e") and n > 1:
        n -= 1
    return max(1, n)

def _fk_grade(text):
    if _HAS_TEXTSTAT:
        return round(textstat.flesch_kincaid_grade(text), 1)
    words = re.findall(r"[A-Za-z]+", text)
    sents = _split_sentences(text) or [text]
    syll = sum(_syllables(w) for w in words) or 1
    wc = len(words) or 1
    return round(0.39 * (wc / len(sents)) + 11.8 * (syll / wc) - 15.59, 1)

def measure(text):
    sents = _split_sentences(text)
    if not sents:
        return None
    wcs = [len(re.findall(r"[A-Za-z']+", s)) for s in sents]
    cls = [_count_clauses(s) for s in sents]
    return {
        "wc":      len(re.findall(r"[A-Za-z']+", text)),
        "avg":     round(sum(wcs) / len(wcs), 1),
        "max":     max(wcs),
        "clauses": max(cls),
        "fk":      _fk_grade(text),
        "sents":   len(sents),
    }


TARGETS = [
    {"sheet": "JUNIOR",   "level_val": "LEVEL 2", "label": "JUNIOR L2"},
    {"sheet": "JUNIOR M", "level_val": "LEVEL 1", "label": "JUNIOR M L1"},
]

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)

for cfg in TARGETS:
    ws  = wb[cfg["sheet"]]
    rows = list(ws.iter_rows(values_only=True))
    hdr  = [str(c).strip() if c else "" for c in rows[0]]
    lv_col = next((i for i, h in enumerate(hdr) if "레벨" in h or "level" in h.lower()), None)
    tx_col = next((i for i, h in enumerate(hdr) if "본문" in h or "text" in h.lower()), None)

    print(f"\n=== {cfg['label']} (시트={cfg['sheet']}, 레벨컬=col{lv_col}, 본문컬=col{tx_col}) ===")
    if lv_col is None or tx_col is None:
        print("  헤더 컬럼을 찾지 못했습니다.")
        continue

    results = []
    for r in rows[1:]:
        if not r or len(r) <= max(lv_col, tx_col):
            continue
        lv = str(r[lv_col]).strip() if r[lv_col] else ""
        if lv != cfg["level_val"]:
            continue
        text = str(r[tx_col]).strip() if r[tx_col] else ""
        if len(text) < 50:
            continue
        m = measure(text)
        if m:
            results.append(m)

    if not results:
        print("  해당 레벨 기사 없음")
        continue

    fks = sorted(r["fk"] for r in results)
    avgs = sorted(r["avg"] for r in results)
    maxs = sorted(r["max"] for r in results)
    cls_ = sorted(r["clauses"] for r in results)

    p50 = lambda xs: xs[len(xs)//2]
    p90 = lambda xs: xs[int(len(xs)*0.9)]

    print(f"  기사 수: {len(results)}")
    print(f"  FK grade — min={min(fks):.1f} / p50={p50(fks):.1f} / p90={p90(fks):.1f} / max={max(fks):.1f}")
    print(f"  avg sent — min={min(avgs):.1f} / p50={p50(avgs):.1f} / p90={p90(avgs):.1f} / max={max(avgs):.1f}")
    print(f"  max sent — min={min(maxs)}  / p50={p50(maxs)}  / p90={p90(maxs)}  / max={max(maxs)}")
    print(f"  max cl   — min={min(cls_)}  / p50={p50(cls_)}  / p90={p90(cls_)}  / max={max(cls_)}")
    print(f"  (cefr_checker 현재 fk_max: JUNIOR_L2=8.5 / JUNIORM_L1=8.5)")
