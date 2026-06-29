"""cefrpy로 guidelines NOT/USE/domain 단어 CEFR 레벨 조회."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import cefrpy

analyzer = cefrpy.CEFRAnalyzer()

def get_cefr(word):
    """단어의 CEFR 레벨 반환. 미수록이면 None."""
    w = word.lower().strip()
    if not analyzer.is_word_in_database(w):
        return None
    # 모든 POS에서 레벨 수집
    levels = []
    for pos_id in range(10):  # POSTag enum 범위
        try:
            lv = analyzer.get_word_pos_level_CEFR(w, pos_id)
            if lv and str(lv).strip() not in ("", "None"):
                levels.append(str(lv))
        except Exception:
            pass
    if levels:
        # 가장 낮은 레벨(=학습자에게 가장 쉬운 사용)을 대표값으로
        order = ["A1","A2","B1","B2","C1","C2"]
        sorted_lvs = sorted(set(levels), key=lambda x: order.index(x) if x in order else 9)
        return sorted_lvs[0] if sorted_lvs else levels[0]
    return None

# --- cefrpy POSTag 확인 ---
print("POSTag:", [(p.name, p.value) for p in cefrpy.POSTag])
print()

# POSTag 기반으로 다시
def get_cefr_v2(word):
    w = word.lower().strip()
    if not analyzer.is_word_in_database(w):
        return None
    levels = []
    for pos in cefrpy.POSTag:
        try:
            lv = analyzer.get_word_pos_level_CEFR(w, pos)
            if lv is not None:
                s = str(lv).strip()
                if s not in ("", "None"):
                    levels.append(s)
        except Exception:
            pass
    if not levels:
        return "(수록·레벨없음)"
    order = ["A1","A2","B1","B2","C1","C2"]
    sorted_lvs = sorted(set(levels), key=lambda x: order.index(x) if x in order else 9)
    return sorted_lvs[0]

# 샘플 테스트
for w in ["say","proliferation","proponents","surveillance","GDP"]:
    print(f"  {w}: {get_cefr_v2(w)}")
print()

# ── 조회 대상 ─────────────────────────────────────────────────────────────
# (guidelines 원문에서 추출, 복합구는 구성어 개별 조회)
NOT_L1 = [
    "proponents",
    "deterring",          # deter의 동명사
    "incorporating",      # incorporate의 동명사
    "measurable",         # "measurable margins"
    "margins",
    "advocates",          # "civil liberties advocates"
]
NOT_L23 = [
    "proliferation",
    "contend",
    "criminologists",
    "conducted",
]
USE_L1 = [
    "supporters",
    "stopping",           # stop의 동명사
    "using",
    "privacy",
    "groups",
]
USE_L23 = [
    "say",
    "keep",
    "pace",
    "installed",          # "cameras are being installed"
    "show",               # "Studies ... show that"
]
DOMAIN_OK = [
    "GDP",
    "legislation",
    "surveillance",
]

SECTIONS = [
    ("NOT 단어 — L1 금지 (기대: C1+)",              NOT_L1),
    ("NOT 단어 — L2/L3 금지 (기대: C1+)",           NOT_L23),
    ("USE 대체어 — L1 (기대: B1 이하)",              USE_L1),
    ("USE 대체어 — L2/L3 (기대: B2 이하)",           USE_L23),
    ("Domain terms — B2 허용 (기대: B2 이하)",       DOMAIN_OK),
]

for label, words in SECTIONS:
    print(f"\n{'─'*58}")
    print(f"  {label}")
    print(f"{'─'*58}")
    print(f"  {'단어':<24} {'레벨':>8}  {'정합':>6}")
    print(f"{'─'*58}")
    missing = 0
    for w in words:
        lv = get_cefr_v2(w)
        order = ["A1","A2","B1","B2","C1","C2"]
        if lv is None:
            lv_str = "(미수록)"
            flag = "?"
            missing += 1
        else:
            lv_str = lv
            # 정합 판단
            if "NOT" in label and "기대: C1+" in label:
                flag = "OK" if lv in ("C1","C2") else "주의"
            elif "USE" in label and "B1" in label:
                flag = "OK" if lv in ("A1","A2","B1") else "주의"
            elif "USE" in label and "B2" in label:
                flag = "OK" if lv in ("A1","A2","B1","B2") else "주의"
            elif "Domain" in label:
                flag = "OK" if lv in ("A1","A2","B1","B2") else "참고"
            else:
                flag = "-"
        print(f"  {w:<24} {lv_str:>8}  {flag:>6}")
    print(f"  미수록: {missing}/{len(words)}건")

print("\n=== 완료 ===")
