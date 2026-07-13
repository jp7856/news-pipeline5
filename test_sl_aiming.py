"""sl 조준점 파싱 수정 검증 — TIMES L1/L2/L3 + KINDER L1 + KIDS L1

확인 항목:
  [A] sl 재작성 노트에 "around N words" 숫자가 실제로 들어가는지
      (이전: 항상 fallback "the middle of..." — 이번 수정이 처음으로 숫자를 넣음)
  [B] sl이 여전히 수렴하는지 (진동 없음)
  [C] KINDER/KIDS도 파싱 수정 후 sl이 달라지지 않는지

실행:
  python test_sl_aiming.py
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

RUNS = [
    (Level.TIMES,  "L1", "The James Webb Space Telescope and its discoveries about the early universe", Section.SCIENCE),
    (Level.TIMES,  "L2", "The Pacific Ocean's five major gyres and ocean plastic pollution",            Section.ENVIRONMENT),
    (Level.TIMES,  "L3", "The impact of social media algorithms on political polarization",             Section.SOCIETY),
    (Level.KINDER, "L1", "Why bees are important for flowers and food",                                 Section.SCIENCE),
    (Level.KIDS,   "L1", "How earthquakes happen and how scientists measure them",                      Section.SCIENCE),
]

_summary: list[dict] = []


def run_one(level: Level, sub_level: str, topic: str, section: Section):
    label = f"{level.value.upper()} {sub_level}"
    logs: list[str] = []

    def capture(msg: str):
        logs.append(msg)
        print(msg)

    print(f"\n{'=' * 70}")
    print(f"  {label}  |  {topic[:55]}")
    print(f"{'=' * 70}")

    package = None
    completed = False
    try:
        orc = Orchestrator(log_callback=capture)
        state = orc.run_phase1(topic=topic, level=level, section=section, sub_level=sub_level)
        package, _ = orc.run_phase2(state)
        completed = True
    except Exception as e:
        err_str = str(e)
        is_sheets = any(k in err_str.lower() for k in ("sheet", "google", "credentials", "gspread"))
        if is_sheets:
            print(f"\n[INFO] Sheets 저장 실패 (로컬 미설정) — 그 이전 단계 기준으로 분석")
        else:
            print(f"\n[ERROR] {e}")
            import traceback; traceback.print_exc()

    print(f"\n{'─' * 60}")
    print(f"[RESULT] {label}")

    # ── [A] sl 재작성 조준점 로그 ──────────────────────────────────────
    aim_logs = [l.strip() for l in logs if "sl 재작성 조준점" in l]
    print(f"\n[A] sl 재작성 조준점 로그:")
    if aim_logs:
        for l in aim_logs:
            # 핵심: "around N" 또는 "the middle of" 중 무엇이 출력됐나
            if "around" in l:
                print(f"    OK 숫자: {l}")
            else:
                print(f"    FALLBACK: {l}")
    else:
        print("    sl 재작성 미발생 (1회 통과)")

    # ── [B] sl 회차별 수렴 ─────────────────────────────────────────────
    sl_entries: list[tuple[int, float]] = []
    for l in logs:
        m = re.search(r"평균 문장 길이 ([\d.]+)단어.*재작성 (\d+)/", l)
        if m:
            sl_entries.append((int(m.group(2)), float(m.group(1))))

    rewrite_count = max(n for n, _ in sl_entries) if sl_entries else 0

    if package:
        from agents.sub_agents.writer import WriterAgent
        final_sl = WriterAgent._avg_sentence_length(package.article.text)
        _cfg, _ = WriterAgent._merge_config(level, sub_level)
        sl_range = _cfg.get("sentence_length", "?")
    else:
        final_sl = None
        sl_range = "?"

    print(f"\n[B] Phase1 재작성 횟수: {rewrite_count}회")
    if sl_entries:
        for attempt_no, sl_val in sorted(sl_entries):
            print(f"    재작성 {attempt_no}회차 직전 avg_sl: {sl_val:.1f}")
    if final_sl is not None:
        in_range_mark = "✓" if _in_range(final_sl, sl_range) else "⚠ 범위 이탈"
        print(f"    최종 avg_sl: {final_sl:.1f}  (목표 {sl_range}) {in_range_mark}")
    else:
        print("    (package 없어 최종값 계산 불가)")

    # Phase2 Reviser 재작성 로그
    phase2_rewrites = [l.strip() for l in logs if "검수 거부" in l and "재작성" in l]
    if phase2_rewrites:
        print(f"\n    [Phase2 재작성]")
        for l in phase2_rewrites:
            print(f"      {l}")

    # ── [C] wc 최종 확인 ───────────────────────────────────────────────
    if package:
        from agents.sub_agents.writer import WriterAgent as _WA
        _cfg2, _ = _WA._merge_config(level, sub_level)
        wc_range = _cfg2.get("word_count_range", "")
        wc_ok = _WA._word_count_in_range(package.article.word_count, wc_range)
        print(f"\n[C] 최종 wc={package.article.word_count} (목표 {wc_range}) {'✓' if wc_ok else '⚠ 범위 이탈'}")

    # ── 검수 결과 ──────────────────────────────────────────────────────
    if package and package.review_result:
        rv = package.review_result
        status = "승인" if rv.passed else f"거부: {rv.notes[:100]}"
        print(f"    검수: {status}")

    # ── 비용 ───────────────────────────────────────────────────────────
    from agents.sub_agents.usage_tracker import usage_cost, usage_summary
    cost = usage_cost()
    print(f"\n    비용: ${cost['usd']:.4f} ({cost['krw']:,}원)  {usage_summary()}")

    print(f"{'─' * 60}")

    _summary.append({
        "label": label,
        "rewrite": rewrite_count,
        "aim_ok": any("around" in l for l in aim_logs),
        "aim_fallback": any("around" not in l for l in aim_logs) and bool(aim_logs),
        "no_sl_rewrite": not aim_logs,
        "final_sl": f"{final_sl:.1f}" if final_sl is not None else "-",
        "sl_range": sl_range,
        "sl_ok": _in_range(final_sl, sl_range) if final_sl else None,
        "wc": package.article.word_count if package else "-",
        "review": "승인" if (package and package.review_result and package.review_result.passed) else "거부",
        "usd": f"${cost['usd']:.4f}",
    })


def _in_range(val: float, range_str: str) -> bool:
    try:
        nums = re.findall(r"\d+", range_str)
        return float(nums[0]) <= val <= float(nums[1])
    except Exception:
        return True


if __name__ == "__main__":
    for level, sub_level, topic, section in RUNS:
        run_one(level, sub_level, topic, section)

    print(f"\n{'=' * 70}")
    print("  5건 요약")
    print(f"{'=' * 70}")
    hdr = f"{'레벨':<13} {'재작성':>5} {'조준점':>8} {'최종sl':>7} {'sl범위':>12} {'sl✓':>4} {'검수':>4} {'비용':>9}"
    print(hdr)
    print("-" * len(hdr))
    for r in _summary:
        if r["no_sl_rewrite"]:
            aim = "미발생"
        elif r["aim_ok"]:
            aim = "숫자OK"
        else:
            aim = "fallback"
        sl_ok_mark = "✓" if r["sl_ok"] else ("⚠" if r["sl_ok"] is False else "-")
        print(
            f"{r['label']:<13} {r['rewrite']:>5} {aim:>8} {r['final_sl']:>7} "
            f"{r['sl_range']:>12} {sl_ok_mark:>4} {r['review']:>4} {r['usd']:>9}"
        )
    print()
    print("조준점 판정 기준: '숫자OK'=around N words 실제 반영, 'fallback'=the middle of... 여전히 사용, '미발생'=sl 재작성 없었음")
