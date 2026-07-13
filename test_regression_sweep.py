"""회귀 검증 — 전 매체 × 대표 레벨 1건씩.

오늘 수정한 것: sl_aim_hint 공유, Reviser 영어 지시문, Editor wc 체크, sl 파싱 수정.
초점: "이 매체를 깨뜨리진 않았나" — 최종 Agent5 승인 여부는 부차적.

확인 항목 (매체 무관):
  1) crash 없나
  2) sl이 자기 매체 범위 안에 드나 (0.5 조준점이 자기 범위로 맞는지 포함)
  3) Phase2 Reviser 재작성 정상 도나 (답변만/에러 없나)
  4) JSON 파싱 에러 없나
  5) BRIEF/DIALOGUE(비정형) 분류가 뜨는지, 뜬다면 sl 조준점이 이상 작동하는지

실행: python test_regression_sweep.py
"""
import re
import sys
import os
import io

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))

from models import Level, Section
from orchestrator import Orchestrator
from agents.sub_agents.writer import WriterAgent

RUNS = [
    (Level.KINDER,   "L1", "How caterpillars turn into butterflies", Section.SCIENCE),
    (Level.KIDS,     "L1", "Why the moon looks different every night", Section.SCIENCE),
    (Level.JUNIOR,   "L2", "How recycling programs are changing in Korean cities", Section.SOCIETY),
    (Level.JUNIOR,   "L3", "How young people are getting involved in local politics", Section.SOCIETY),
    (Level.JUNIOR_M, "L1", "The debate over school smartphone bans in Korea", Section.EDUCATION),
    (Level.TIMES,    "L2", "How AI-generated content is challenging copyright law", Section.TECHNOLOGY),
]

_summary = []


def _in_range(val, range_str):
    try:
        nums = re.findall(r"\d+", range_str)
        return float(nums[0]) <= val <= float(nums[1])
    except Exception:
        return None


def run_one(level, sub_level, topic, section):
    label = f"{level.value.upper()} {sub_level}"
    logs = []
    crashed = False
    crash_msg = ""

    def capture(msg):
        logs.append(msg)
        print(msg)

    print(f"\n{'=' * 72}")
    print(f"  {label}  |  {topic[:52]}")
    print(f"{'=' * 72}")

    package = None
    completed = False
    try:
        orc = Orchestrator(log_callback=capture)
        state = orc.run_phase1(topic=topic, level=level, section=section, sub_level=sub_level)
        package, _ = orc.run_phase2(state)
        completed = True
    except Exception as e:
        err_str = str(e)
        if any(k in err_str.lower() for k in ("sheet", "google", "credentials", "gspread")):
            print(f"\n[INFO] Sheets 저장 실패 (로컬 미설정) — 그 이전 단계 기준 분석")
        else:
            crashed = True
            crash_msg = err_str[:150]
            print(f"\n[CRASH] {e}")
            import traceback; traceback.print_exc()

    print(f"\n{'─' * 62}")
    print(f"[RESULT] {label}")

    # ── JSON 파싱 에러 ────────────────────────────────────────────────
    parse_err_logs = [l.strip() for l in logs if "파싱 실패" in l or "JSON" in l and ("실패" in l or "에러" in l)]
    truncation_logs = [l.strip() for l in logs if "잘렸습니다" in l or "잘림" in l]

    # ── BRIEF/DIALOGUE 비정형 분류 ────────────────────────────────────
    nonstandard_logs = [l.strip() for l in logs if "유형=BRIEF" in l or "유형=DIALOGUE" in l]

    # ── Phase1 재작성 ─────────────────────────────────────────────────
    p1_nums = [int(m) for l in logs for m in re.findall(r"재작성 (\d+)/3회", l)]
    p1_rewrites = max(p1_nums) if p1_nums else 0

    # ── sl 조준점 로그 ────────────────────────────────────────────────
    sl_aim_logs = [l.strip() for l in logs if "sl 재작성 조준점" in l]

    # ── Phase2 Reviser 행동 ───────────────────────────────────────────
    rewrote_cnt = len(re.findall(r"\[Reviser\] 수정 완료", "\n".join(logs)))
    answer_only_cnt = len(re.findall(r"\[Reviser\] 답변만 제공", "\n".join(logs)))
    reviser_err_logs = [l.strip() for l in logs if "Reviser" in l and ("오류" in l or "에러" in l or "실패" in l)]

    print(f"\n[1] Crash: {'❌ ' + crash_msg if crashed else '✓ 없음'}")

    print(f"\n[2] sl 범위 확인:")
    if package:
        final_sl = WriterAgent._avg_sentence_length(package.article.text)
        _cfg, _ = WriterAgent._merge_config(level, sub_level)
        sl_range = _cfg.get("sentence_length", "")
        wc_range = _cfg.get("word_count_range", "")
        sl_ok = _in_range(final_sl, sl_range)
        final_wc = package.article.word_count
        wc_ok = _in_range(final_wc, wc_range)
        print(f"    sl={final_sl:.1f} (목표 {sl_range}) {'✓' if sl_ok else '⚠ 이탈'}")
        print(f"    wc={final_wc} (목표 {wc_range}) {'✓' if wc_ok else '⚠ 이탈'}")
    else:
        final_sl = final_wc = sl_range = wc_range = None
        sl_ok = wc_ok = None
        print("    (package 없음 — 계산 불가)")

    print(f"\n[3] Phase2 Reviser: 재작성 {rewrote_cnt}회 / 답변만 {answer_only_cnt}회")
    if reviser_err_logs:
        for l in reviser_err_logs:
            print(f"    ⚠ {l}")

    print(f"\n[4] JSON 파싱/잘림 에러:")
    if parse_err_logs or truncation_logs:
        for l in parse_err_logs + truncation_logs:
            print(f"    ⚠ {l}")
    else:
        print("    없음")

    print(f"\n[5] 비정형(BRIEF/DIALOGUE) 분류:")
    if nonstandard_logs:
        for l in nonstandard_logs:
            print(f"    ⚡ {l}")
        if sl_aim_logs:
            print(f"    → 비정형 감지된 상태에서 sl 조준점도 발생함 (아래 [sl조준점] 참고)")
    else:
        print("    없음 (표준 산문으로 분류)")

    print(f"\n[Phase1] 재작성 {p1_rewrites}/3회")
    print(f"[sl조준점] {len(sl_aim_logs)}회 발생")
    for l in sl_aim_logs:
        print(f"    {l}")

    if package and package.review_result:
        passed = package.review_result.passed
        print(f"\n[참고] Agent5: {'승인' if passed else '거부'}")

    from agents.sub_agents.usage_tracker import usage_cost
    cost = usage_cost()
    print(f"\n    비용: ${cost['usd']:.4f} ({cost['krw']:,}원)")
    print(f"{'─' * 62}")

    _summary.append({
        "label": label,
        "crashed": crashed,
        "sl": f"{final_sl:.1f}" if final_sl is not None else "-",
        "sl_range": sl_range or "-",
        "sl_ok": sl_ok,
        "wc": final_wc if final_wc is not None else "-",
        "wc_ok": wc_ok,
        "p1_rewrites": p1_rewrites,
        "rewrote": rewrote_cnt,
        "answer_only": answer_only_cnt,
        "parse_err": bool(parse_err_logs or truncation_logs),
        "nonstandard": len(nonstandard_logs),
        "sl_aim_cnt": len(sl_aim_logs),
        "usd": f"${cost['usd']:.4f}",
    })


if __name__ == "__main__":
    for level, sub_level, topic, section in RUNS:
        run_one(level, sub_level, topic, section)

    print(f"\n{'=' * 72}")
    print("  6건 회귀 요약")
    print(f"{'=' * 72}")
    hdr = f"{'레벨':<11} {'crash':>5} {'sl':>6} {'범위':>10} {'✓':>2} {'wc':>4} {'✓':>2} {'P1':>3} {'재작성':>4} {'답변만':>4} {'parse':>5} {'비정형':>4} {'조준':>3}"
    print(hdr)
    print("-" * len(hdr))
    for r in _summary:
        def mark(v):
            return "✓" if v is True else ("⚠" if v is False else "-")
        print(
            f"{r['label']:<11} {'❌' if r['crashed'] else '✓':>5} {r['sl']:>6} "
            f"{r['sl_range']:>10} {mark(r['sl_ok']):>2} {str(r['wc']):>4} {mark(r['wc_ok']):>2} "
            f"{r['p1_rewrites']:>3} {r['rewrote']:>4} {r['answer_only']:>4} "
            f"{'⚠' if r['parse_err'] else '✓':>5} {r['nonstandard']:>4} {r['sl_aim_cnt']:>3}"
        )
    print()
    print("판정: crash=❌면 즉시 이슈 / sl·wc ⚠면 범위 이탈 / 답변만>0이면 Reviser path2 재발 / parse=⚠면 파싱·잘림 에러 / 비정형>0이면 BRIEF·DIALOGUE 감지됨(정상일 수 있음, 조준점과 충돌 여부 별도 확인)")
