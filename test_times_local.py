"""로컬 검증 스크립트 — TIMES L1/L2/L3 각 1건 생성.

확인 항목:
  1) 3건 순차 실행
  2) Phase1 재작성 횟수 (실제 회차 수)
  3) sl 회차별 추이 (값 파싱)
  4) Editor 교정 후 wc 유지 여부
  5) Agent5 JSON 파싱 에러
  6) 비용 건별 ($)

실행:
  python test_times_local.py
"""
import re
import sys
import os
import io

# Windows cp949 출력 문제 방지
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))

from models import Level, Section
from orchestrator import Orchestrator

TOPIC = "The Pacific Ocean's five major gyres and ocean plastic pollution"
SECTION = Section.ENVIRONMENT

RUNS = [
    ("L1", "TIMES L1 (110-150 wc, sl 13-18)"),
    ("L2", "TIMES L2 (260-300 wc, sl 15-20)"),
    ("L3", "TIMES L3 (280-310 wc, sl 16-20)"),
]

# 건별 요약 (마지막에 3건 나란히 출력)
_summary: list[dict] = []


def run_one(sub_level: str, label: str):
    logs: list[str] = []

    def capture(msg: str):
        logs.append(msg)
        print(msg)

    print(f"\n{'=' * 70}")
    print(f"  {label}")
    print(f"{'=' * 70}")

    package = None
    completed = False
    try:
        orc = Orchestrator(log_callback=capture)
        state = orc.run_phase1(
            topic=TOPIC,
            level=Level.TIMES,
            section=SECTION,
            sub_level=sub_level,
        )
        package, _sheet_url = orc.run_phase2(state)
        completed = True
    except Exception as e:
        err_str = str(e)
        is_sheets_err = any(k in err_str.lower() for k in ("sheet", "google", "credentials", "gspread"))
        if is_sheets_err:
            print(f"\n[INFO] Worksheet 저장 실패 (로컬 Sheets 미설정) — 이하 분석은 그 앞 단계 기준")
        else:
            print(f"\n[ERROR] {e}")
            import traceback
            traceback.print_exc()

    # ── 분석 섹션 ──────────────────────────────────────────────────────────
    print(f"\n{'─' * 60}")
    print(f"[RESULT] {label}")

    # ── [2] 재작성 횟수 ─────────────────────────────────────────────────────
    # 로그 패턴: "재작성 N/3회"  → max N = 실제 재작성 횟수
    attempt_nums = [int(m) for l in logs for m in re.findall(r"재작성 (\d+)/\d+회", l)]
    rewrite_count = max(attempt_nums) if attempt_nums else 0
    # 트리거 종류 (wc/sl/표절/CEFR)
    trigger_logs = [
        l.strip() for l in logs
        if ("워드카운트" in l or "평균 문장 길이" in l or "표절 위험" in l or "CEFR 난이도" in l)
        and "재작성" in l
    ]
    print(f"\n[2] Phase1 재작성 횟수: {rewrite_count}회 / 최대 3회")
    if trigger_logs:
        for l in trigger_logs:
            print(f"    {l}")
    else:
        print("    트리거 없음 — 1회 통과")

    # ── [3] sl 회차별 추이 ──────────────────────────────────────────────────
    # 로그: "[...] 평균 문장 길이 X.X단어 목표(Y-Z) 벗어남 — 재작성 N/M회"
    sl_entries: list[tuple[int, float]] = []
    for l in logs:
        m = re.search(r"평균 문장 길이 ([\d.]+)단어.*재작성 (\d+)/", l)
        if m:
            sl_entries.append((int(m.group(2)), float(m.group(1))))
    # 통과 시 avg_sl: package가 있으면 직접 계산
    if package:
        from agents.sub_agents.writer import WriterAgent
        final_sl = WriterAgent._avg_sentence_length(package.article.text)
    else:
        final_sl = None

    print(f"\n[3] sl 회차별 추이:")
    if sl_entries:
        for attempt_no, sl_val in sorted(sl_entries):
            print(f"    재작성 {attempt_no}회차 직전 avg_sl: {sl_val:.1f}단어")
    else:
        print("    sl 범위 이탈 없음 (재작성 미발생)")
    if final_sl is not None:
        _cfg, _ = __import__("agents.sub_agents.writer", fromlist=["WriterAgent"]).WriterAgent._merge_config(Level.TIMES, sub_level)
        sl_range = _cfg.get("sentence_length", "?")
        print(f"    최종 avg_sl: {final_sl:.1f}단어 (목표 {sl_range})")
    elif not sl_entries:
        print("    (package 없어 최종값 계산 불가)")

    # ── [4] Editor 교정 결과 ────────────────────────────────────────────────
    # "교정 N건 본문 반영" 또는 "교정 건너뜀" 로그
    editor_applied_logs = [l.strip() for l in logs if "교정" in l and "반영" in l]
    editor_skip_logs = [l.strip() for l in logs if "교정 건너뜀" in l]
    # Pipeline Complete 의 "Edits : N suggestions" → Editor가 제안 자체를 했는지 확인
    edits_total_logs = [l.strip() for l in logs if "Edits" in l and "suggestions" in l]

    print(f"\n[4] Editor 교정 결과:")
    if edits_total_logs:
        for l in edits_total_logs:
            print(f"    {l}")
    if editor_applied_logs:
        for l in editor_applied_logs:
            print(f"    {l}")
    if editor_skip_logs:
        for l in editor_skip_logs:
            print(f"    {l}")
    if not edits_total_logs and not editor_applied_logs and not editor_skip_logs:
        print("    교정 관련 로그 없음")
    # wc 범위 유지 확인: Pipeline Complete의 Article wc와 목표 범위 비교
    if package:
        from agents.sub_agents.writer import WriterAgent as _WA
        _cfg2, _ = _WA._merge_config(Level.TIMES, sub_level)
        wc_range = _cfg2.get("word_count_range", "")
        wc_ok = _WA._word_count_in_range(package.article.word_count, wc_range)
        print(f"    최종 wc={package.article.word_count} (목표 {wc_range}) → {'범위 내' if wc_ok else '⚠️ 범위 이탈'}")

    # ── [5] Agent5 파싱/잘림 ────────────────────────────────────────────────
    agent5_errors = [l.strip() for l in logs if "Agent5" in l and ("파싱" in l or "잘렸" in l or "재요청" in l)]
    agent5_result = [l.strip() for l in logs if "Agent5" in l and ("승인" in l or "거부" in l or "검수 완료" in l)]
    print(f"\n[5] Agent5 파싱/잘림 이상:")
    if agent5_errors:
        for l in agent5_errors:
            print(f"    ⚠️ {l}")
    else:
        print("    없음 — 정상 처리")
    for l in agent5_result:
        print(f"    → {l}")

    # ── [6] 비용 건별 ────────────────────────────────────────────────────────
    # reset_usage()는 run_phase1() 시작 시 자동 호출 → 이 값은 해당 건 단독 비용
    from agents.sub_agents.usage_tracker import usage_summary, usage_cost
    cost_info = usage_cost()
    usd = cost_info.get("usd", 0)
    krw = cost_info.get("krw", 0)
    status_tag = "" if completed else " (Phase2 미완료 — Sheets 실패 직전까지)"
    print(f"\n[6] 비용 [{sub_level}]{status_tag}: ${usd:.4f} (약 {krw:,.0f}원)")
    # usage_summary 한 줄 (API 호출 횟수 포함)
    print(f"    {usage_summary()}")

    # ── 최종 기사 요약 ────────────────────────────────────────────────────────
    print(f"\n[ARTICLE]")
    if package:
        art = package.article
        review = package.review_result
        print(f"    wc={art.word_count}, sub_level={package.sub_level}")
        if review:
            status = "승인" if review.passed else f"거부 ({review.notes[:80]})"
            print(f"    검수: {status}")
    else:
        wc_log = next((l.strip() for l in logs if "Article" in l and "words" in l), None)
        rev_log = next((l.strip() for l in logs if "Agent5" in l and ("승인" in l or "거부" in l)), None)
        if wc_log:
            print(f"    {wc_log}")
        if rev_log:
            print(f"    {rev_log}")

    print(f"{'─' * 60}")

    _summary.append({
        "label": sub_level,
        "rewrite": rewrite_count,
        "final_sl": f"{final_sl:.1f}" if final_sl is not None else "-",
        "wc": package.article.word_count if package else "-",
        "review": ("승인" if package and package.review_result and package.review_result.passed
                   else "거부" if package and package.review_result else "-"),
        "usd": f"${usd:.4f}",
        "krw": f"{krw:,.0f}원",
        "completed": completed,
    })


if __name__ == "__main__":
    for sub_level, label in RUNS:
        run_one(sub_level, label)

    # ── 3건 요약 테이블 ──────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("  3건 요약")
    print(f"{'=' * 70}")
    hdr = f"{'레벨':<6} {'재작성':>6} {'최종sl':>7} {'wc':>5} {'검수':>4} {'비용($)':>10} {'비용(원)':>10} {'완료':>4}"
    print(hdr)
    print("-" * len(hdr))
    for r in _summary:
        row = (
            f"{r['label']:<6} {r['rewrite']:>6} {r['final_sl']:>7} "
            f"{str(r['wc']):>5} {r['review']:>4} {r['usd']:>10} {r['krw']:>10} "
            f"{'Y' if r['completed'] else 'N':>4}"
        )
        print(row)
    print()
