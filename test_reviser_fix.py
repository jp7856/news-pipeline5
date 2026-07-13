"""7f844d8 검증 — Phase2 Reviser 재작성 지시문 영어 명령형 변경.

핵심 질문: Reviser가 "고치는 것" vs "고쳐서 Agent5 검수 통과하는 것"은 다르다.
  → 재작성 여부 + wc/sl 실제 변화 + 최종 Agent5 승인까지 함께 본다.

RUNS:
  1) TIMES L3 — 방금 312로 거부났던 조건 (wc 상한 초과)
  2) TIMES L1 — Phase2 Reviser가 sl 이탈시켜 거부됐던 케이스 (sl 거부 범용성)
  3) KINDER L1 — 영어 명령형 지시문 후 한국어 답변/생성 무영향 실증

실행: python test_reviser_fix.py
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
    (Level.TIMES,  "L3", "The impact of social media algorithms on political polarization", Section.SOCIETY),
    (Level.TIMES,  "L1", "The James Webb Space Telescope and its discoveries about the early universe", Section.SCIENCE),
    (Level.KINDER, "L1", "Why bees are important for flowers and food", Section.SCIENCE),
]

_summary: list[dict] = []


def _in_range(val, range_str):
    try:
        nums = re.findall(r"\d+", range_str)
        return float(nums[0]) <= val <= float(nums[1])
    except Exception:
        return None


def run_one(level, sub_level, topic, section):
    label = f"{level.value.upper()} {sub_level}"
    logs = []

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
        if any(k in str(e).lower() for k in ("sheet", "google", "credentials", "gspread")):
            print(f"\n[INFO] Sheets 저장 실패 (로컬 미설정) — 그 이전 단계 기준 분석")
        else:
            print(f"\n[ERROR] {e}")
            import traceback; traceback.print_exc()

    print(f"\n{'─' * 62}")
    print(f"[RESULT] {label}")

    # ── Phase1 재작성 횟수 ────────────────────────────────────────────
    p1_nums = [int(m) for l in logs for m in re.findall(r"재작성 (\d+)/3회", l)]
    p1_rewrites = max(p1_nums) if p1_nums else 0

    # ── Phase2 Reviser 회차별 추적 ────────────────────────────────────
    # 이벤트를 순서대로 파싱: 검수거부 → Reviser 수정완료/답변만 → 설명 → 승인/거부
    p2_events = []  # (type, detail)
    for l in logs:
        m_rej = re.search(r"\[Phase2\] 검수 거부 — 재작성 (\d+)/(\d+)회", l)
        if m_rej:
            p2_events.append(("reject", f"{m_rej.group(1)}/{m_rej.group(2)}"))
        m_fixed = re.search(r"\[Reviser\] 수정 완료 — (\d+)단어", l)
        if m_fixed:
            p2_events.append(("rewrote", int(m_fixed.group(1))))
        if "[Reviser] 답변만 제공" in l:
            p2_events.append(("answer_only", None))
        m_expl = re.search(r"\[Reviser\] 설명: (.+)", l)
        if m_expl:
            p2_events.append(("reply", m_expl.group(1).strip()))
        if "재작성 2회 후에도 검수 거부" in l:
            p2_events.append(("exhausted", None))

    rewrote_cnt = sum(1 for t, _ in p2_events if t == "rewrote")
    answer_only_cnt = sum(1 for t, _ in p2_events if t == "answer_only")
    reviser_wcs = [d for t, d in p2_events if t == "rewrote"]
    replies = [d for t, d in p2_events if t == "reply"]

    print(f"\n[Phase1] 재작성 {p1_rewrites}/3회")
    print(f"\n[Phase2 Reviser 행동]")
    if not p2_events:
        print("    Phase2 재작성 미발생 (Agent5 1회 통과)")
    else:
        for t, d in p2_events:
            if t == "reject":
                print(f"    ✗ 검수 거부 → 재작성 {d} 시도")
            elif t == "rewrote":
                print(f"      → Reviser 재작성함: {d}단어")
            elif t == "answer_only":
                print(f"      → ⚠ Reviser 답변만 제공 (기사 변경 없음)")
            elif t == "reply":
                print(f"      → 설명(한국어?): {d[:80]}")
            elif t == "exhausted":
                print(f"    ✗✗ 재작성 소진 — 최종 검수거부 저장")
    print(f"\n    재작성 실행: {rewrote_cnt}회 / 답변만: {answer_only_cnt}회")

    # ── 최종 상태 ─────────────────────────────────────────────────────
    if package:
        final_wc = package.article.word_count
        final_sl = WriterAgent._avg_sentence_length(package.article.text)
        _cfg, _ = WriterAgent._merge_config(level, sub_level)
        wc_range = _cfg.get("word_count_range", "")
        sl_range = _cfg.get("sentence_length", "")
        wc_ok = _in_range(final_wc, wc_range)
        sl_ok = _in_range(final_sl, sl_range)
        passed = bool(package.review_result and package.review_result.passed)
        notes = package.review_result.notes if package.review_result else ""

        print(f"\n[최종 상태]")
        print(f"    wc  = {final_wc} (목표 {wc_range}) {'✓' if wc_ok else '⚠ 이탈'}")
        print(f"    sl  = {final_sl:.1f} (목표 {sl_range}) {'✓' if sl_ok else '⚠ 이탈'}")
        print(f"    Agent5 최종: {'✅ 승인' if passed else '❌ 거부'}")
        if not passed:
            print(f"    거부 사유: {notes[:140]}")
    else:
        final_wc = final_sl = wc_range = sl_range = None
        wc_ok = sl_ok = passed = None

    # ── 한국어 답변 확인 (#3) ─────────────────────────────────────────
    ko_reply_ok = None
    if replies:
        # 한글 포함 여부
        ko_reply_ok = any(re.search(r"[가-힣]", r) for r in replies)
        print(f"\n[한국어 답변] Reviser 설명에 한글 포함: {'✓' if ko_reply_ok else '⚠ 한글 없음'}")

    from agents.sub_agents.usage_tracker import usage_cost
    cost = usage_cost()
    print(f"\n    비용: ${cost['usd']:.4f} ({cost['krw']:,}원)")
    print(f"{'─' * 62}")

    _summary.append({
        "label": label,
        "p1": p1_rewrites,
        "rewrote": rewrote_cnt,
        "answer_only": answer_only_cnt,
        "reviser_wcs": reviser_wcs,
        "final_wc": final_wc,
        "final_sl": f"{final_sl:.1f}" if final_sl is not None else "-",
        "wc_ok": wc_ok,
        "sl_ok": sl_ok,
        "passed": passed,
        "ko_reply": ko_reply_ok,
        "usd": f"${cost['usd']:.4f}",
        "completed": completed,
    })


if __name__ == "__main__":
    for level, sub_level, topic, section in RUNS:
        run_one(level, sub_level, topic, section)

    print(f"\n{'=' * 72}")
    print("  3건 요약 — 핵심: 재작성했나 + 검수 통과했나")
    print(f"{'=' * 72}")
    hdr = f"{'레벨':<11} {'P1':>3} {'재작성':>5} {'답변만':>5} {'최종wc':>6} {'wc':>3} {'최종sl':>6} {'sl':>3} {'Agent5':>7} {'한글':>4}"
    print(hdr)
    print("-" * len(hdr))
    for r in _summary:
        def mark(v):
            return "✓" if v is True else ("⚠" if v is False else "-")
        agent5 = "승인" if r["passed"] else ("거부" if r["passed"] is False else "-")
        ko = mark(r["ko_reply"]) if r["ko_reply"] is not None else "n/a"
        print(
            f"{r['label']:<11} {r['p1']:>3} {r['rewrote']:>5} {r['answer_only']:>5} "
            f"{str(r['final_wc']):>6} {mark(r['wc_ok']):>3} {r['final_sl']:>6} {mark(r['sl_ok']):>3} "
            f"{agent5:>7} {ko:>4}"
        )
    print()
    print("판정: 재작성>0 이면 path1 진입 성공 / Agent5 '승인'이 진짜 성공 / 답변만>0 이면 여전히 path2 빠짐")
    # Reviser wc 변화 상세
    for r in _summary:
        if r["reviser_wcs"]:
            print(f"  {r['label']} Reviser wc 변화: {r['reviser_wcs']}")
