"""
_extract_vocab_guardrails 5개 매체 추출 검증.
정확성 확인 후 writer.py 적용 여부 판단에 사용.
"""
import re
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

GUIDELINES_DIR = r"C:\Users\jp\work\news-pipeline5\agents\guidelines"

FILES = [
    ("KINDER",   "agent1_1_kinder.md"),
    ("KIDS",     "agent1_2_kids.md"),
    ("JUNIOR",   "agent1_3_junior.md"),
    ("TIMES",    "agent1_4_times.md"),
    ("JUNIOR M", "agent1_5_junior_m.md"),
]


def load_guideline_body(fname: str) -> str:
    """content_producer.py와 동일: HTML 주석 제거 + strip."""
    with open(f"{GUIDELINES_DIR}\\{fname}", encoding="utf-8") as f:
        text = f.read()
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL).strip()


def _extract_vocab_guardrails(guidelines: str) -> str:
    """writer.py에 추가할 정적 메서드 — 검증용 동일 구현."""
    if not guidelines:
        return ""
    m = re.search(
        r'^[ \t]*-?[ \t]*Vocabulary guardrail',
        guidelines, re.IGNORECASE | re.MULTILINE
    )
    if not m:
        return ""
    start = m.start()
    end_m = re.search(r'\nSub-level differences', guidelines[start:], re.IGNORECASE)
    end = start + end_m.start() if end_m else len(guidelines)
    return guidelines[start:end].strip()


SEP = "=" * 70

for label, fname in FILES:
    body = load_guideline_body(fname)
    extracted = _extract_vocab_guardrails(body)

    print(f"\n{SEP}")
    print(f"매체: {label}  ({fname})")
    print(SEP)
    if not extracted:
        print("  !! 추출 실패 — 섹션을 찾지 못했음")
    else:
        print(extracted)

print(f"\n{SEP}")
print("검증 항목")
print(SEP)
for label, fname in FILES:
    body = load_guideline_body(fname)
    extracted = _extract_vocab_guardrails(body)
    has_not  = "NOT:" in extracted
    has_use  = "USE:" in extracted
    no_sublevels = "Sub-level differences" not in extracted
    found = bool(extracted)
    status = "OK" if (found and has_not and has_use and no_sublevels) else "FAIL"
    print(f"  [{status}] {label:<9} | 추출={found} | NOT={has_not} | USE={has_use} | Sub-level 비침범={no_sublevels}")
