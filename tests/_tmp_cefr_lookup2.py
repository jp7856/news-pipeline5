"""cefrpy(Words-CEFR-Dataset 기반)로 guidelines NOT/USE/domain 단어 레벨 조회."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import cefrpy

# cefrpy API 탐색
print("=== cefrpy API 확인 ===")
print("dir:", [x for x in dir(cefrpy) if not x.startswith("_")])

try:
    a = cefrpy.CEFRAnalyzer()
    print("CEFRAnalyzer OK")
    print("analyzer dir:", [x for x in dir(a) if not x.startswith("_")])
except Exception as e:
    print(f"CEFRAnalyzer 오류: {e}")

# 단순 get_level 시도
test_words = ["proponents", "surveillance", "say", "proliferation"]
for w in test_words:
    try:
        lv = cefrpy.get_level(w)
        print(f"  get_level({w!r}) = {lv}")
    except Exception as e:
        print(f"  get_level({w!r}) 오류: {e}")

try:
    a = cefrpy.CEFRAnalyzer()
    for w in test_words:
        try:
            lv = a.get_level(w)
            print(f"  analyzer.get_level({w!r}) = {lv}")
        except Exception as e:
            print(f"  analyzer.get_level({w!r}) 오류: {e}")
except Exception:
    pass
