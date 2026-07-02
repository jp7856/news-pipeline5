"""run_vocab_review.py — 어휘 드리프트 주간 리뷰 (v3, Railway cron 자동 실행).

⚠ 이 파일 수정 시: push 후 `railway up --service vocab-review-cron` 필요
  (cron 서비스는 푸시 자동 배포 안 됨 — Railway 설계).

매주 일요일 20:00 UTC(= KST 월요일 05:00)에 Railway cron(vocab-review-cron
서비스)이 실행 — KST 월요일 아침 열람 시점에 결과가 준비돼 있도록.
기본 대상: 직전 완결 주 KST 월~일 7일.
수동 실행: railway run python run_vocab_review.py [YYYY-MM | YYYY-MM-DD~YYYY-MM-DD]
생성·발행 파이프라인과 무배선 — 이 파일이 유일한 진입점이다.

동작:
  1. Google Sheets(기존 GOOGLE_SHEETS_CREDENTIALS_JSON / GOOGLE_SHEET_ID 재사용)에서
     대상 기간에 생성된 기사를 읽는다 (원본 시트는 읽기 전용 — 절대 쓰지 않음).
  2. vocab_monitor.check()로 스캔 — flag 로직·시드·임계값은 이 스크립트가 결정하지 않음.
  3. flag(WEAK/STRONG)된 기사를 "Vocab Review" 탭에 1건 1행으로 기록 (없으면 생성).
  4. 실행 요약을 "Run Log" 탭에 남긴다 (flag 0건이어도 남김).
  콘솔에도 같은 내용을 병행 출력 — 탭 쓰기 실패 시에도 결과는 보이게.

baseline_pct = 4.76 (CCTV 767호 실측 기준값 — tests/_tmp_c2va_above_cctv.py의
CCTV_THRESHOLD와 동일). 이 저장소에 이미 존재하던 유일한 실증 기준선을 재사용한
것이며 이 스크립트가 새로 튜닝한 숫자가 아니다. TIMES_L2 실측에서 나온 값이므로
다른 매체의 C2VA 축 판정은 과대/과소 플래그될 수 있다 — C2VA 축은 참고 신호,
독립 축인 SEED_DRIFT는 baseline과 무관하다.

실행:
  python run_vocab_review.py                          # 직전 주 (월~일)
  python run_vocab_review.py 2026-06-22~2026-06-28   # 특정 주 백필
  python run_vocab_review.py 2026-06                 # 월 단위 백필
"""
import io
import json
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else ".")

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import gspread
from google.oauth2.service_account import Credentials

from config import GOOGLE_SHEETS_CREDENTIALS_JSON, GOOGLE_SHEET_ID
from agents.sub_agents import vocab_monitor
from agents.sub_agents.analytical_seed import SEED_WORDS
from agents.sub_agents.article_classifier import classify
from agents.worksheet import SHEET_COLUMNS

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# CCTV 767호 실측 기준 (기존 값 재사용 — 튜닝 아님, 모듈 docstring 참조)
BASELINE_PCT = 4.76

REVIEW_TAB = "Vocab Review"
RUNLOG_TAB = "Run Log"

REVIEW_HEADER = [
    "실행일", "대상 기간", "기사 식별(생성일시)", "토픽", "매체/레벨", "섹션",
    "article_type", "flag", "flag_reason", "판정 축", "확인 위치", "리뷰 액션", "메모",
]
RUNLOG_HEADER = [
    "실행일", "대상 기간", "스캔 기사 수", "carve-out 수",
    "WEAK 수", "STRONG 수", "SEED_DRIFT 단독 승격 수", "시드 집합 스냅샷",
]
REVIEW_ACTIONS = ["정상(오탐)", "드리프트 확인–지침 갱신 필요", "드리프트 확인–시드 후보", "보류"]

# 원본 시트 컬럼 인덱스 — worksheet.SHEET_COLUMNS가 단일 기준
_COL_DATE = SHEET_COLUMNS.index("생성일시")
_COL_LEVEL = SHEET_COLUMNS.index("레벨")
_COL_SECTION = SHEET_COLUMNS.index("섹션")
_COL_TOPIC = SHEET_COLUMNS.index("토픽")
_COL_TEXT = SHEET_COLUMNS.index("기사(영문)")
_COL_SUBLEVEL = SHEET_COLUMNS.index("서브레벨")


def _open_spreadsheet() -> gspread.Spreadsheet:
    """worksheet.py와 동일한 자격증명 처리 (JSON 문자열/파일 경로 겸용)."""
    creds_val = GOOGLE_SHEETS_CREDENTIALS_JSON
    try:
        creds_dict = json.loads(creds_val)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    except (json.JSONDecodeError, TypeError):
        creds = Credentials.from_service_account_file(creds_val, scopes=SCOPES)
    return gspread.authorize(creds).open_by_key(GOOGLE_SHEET_ID)


def _level_key(level: str, sub_level: str) -> str:
    """'junior_m' + 'L1' → 'JUNIORM_L1' (article_classifier.BRIEF_THRESHOLD 키 형식)."""
    sub = sub_level if sub_level in ("L1", "L2", "L3") else "L2"
    return level.replace("_", "").upper() + "_" + sub


def _last_week_window() -> tuple[str, str]:
    """직전 완결 주(월~일)의 KST 날짜 범위를 반환한다.

    실행 시각(UTC)을 KST(+9h)로 변환해 계산한다. Railway cron은 일요일
    20:00 UTC = KST 월요일 05:00에 실행되므로, 그 시점의 '직전 월~일'은
    어제(KST 일요일)로 끝난 주가 된다. 주중 수동 실행 시에도 마지막으로
    완결된 월~일 주를 잡는다(진행 중인 이번 주는 포함하지 않음).
    """
    kst_today = (datetime.now(timezone.utc) + timedelta(hours=9)).date()
    last_monday = kst_today - timedelta(days=kst_today.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)
    return last_monday.isoformat(), last_sunday.isoformat()


def _parse_period(arg: str | None):
    """기간 인자 → (날짜 매칭 함수, 표기 라벨).

    - 없음: 직전 완결 주 KST 월~일 (주간 정기 실행 기본값)
    - "YYYY-MM-DD~YYYY-MM-DD": 명시 구간 (주간 백필/재실행용)
    - "YYYY-MM": 월 단위 (기존 방식 유지 — 월간 백필용)

    비고: 원본 시트 생성일시는 Railway(UTC) 기록이라 KST 주 경계와 최대
    9시간 어긋날 수 있으나, 창들이 날짜 문자열을 빈틈없이 분할하므로
    기사가 두 창에 겹치거나 어느 창에서도 빠지는 일은 없다.
    """
    if arg is None:
        start, end = _last_week_window()
        return (lambda d: start <= d[:10] <= end), f"{start}~{end}"
    if "~" in arg:
        start, end = arg.split("~", 1)
        return (lambda d: start <= d[:10] <= end), f"{start}~{end}"
    return (lambda d: d.startswith(arg)), f"{arg}-01~{arg}-31"


def _axes(r: vocab_monitor.MonitorResult) -> str:
    """판정 근거 축 명시 — C2VA / SEED_DRIFT / 둘 다."""
    c2va_axis = r.above_baseline
    seed_axis = r.seed_hit_count > 0 and not r.seed_carved_out
    if c2va_axis and seed_axis:
        return "C2VA + SEED_DRIFT"
    if seed_axis:
        return "SEED_DRIFT"
    if c2va_axis:
        return "C2VA"
    return "-"


def _get_or_create_tab(ss: gspread.Spreadsheet, title: str, header: list[str], guide: str = ""):
    """탭을 얻거나 생성. 생성 시 (가이드 +) 헤더를 상단에 기록. 반환: (worksheet, created)."""
    try:
        return ss.worksheet(title), False
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=title, rows=200, cols=max(len(header), 8))
        rows = []
        if guide:
            rows += [[line] for line in guide.splitlines()] + [[""]]
        rows.append(header)
        ws.update(values=rows, range_name="A1")
        if guide:
            ws.freeze(rows=len(rows))
        return ws, True


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    date_match, period_label = _parse_period(arg)
    run_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"=== Vocab Review 실행 — 대상 기간: {period_label} ===")

    # 실패 가시성(cron 자동 실행 전제): 스캔·Vocab Review 기록 중 무엇이 죽어도
    # Run Log에는 반드시 행이 남는다(실패 시 FAILED + 에러 1줄). Run Log 기록조차
    # 불가(시트 접근 실패)면 Railway 로그에 [FATAL]을 남기고 exit 1.
    ss: gspread.Spreadsheet | None = None
    error: Exception | None = None
    scanned = carved = weak = strong = seed_only = 0
    try:
        ss = _open_spreadsheet()
        scanned, carved, weak, strong, seed_only = _scan_and_record(
            ss, date_match, run_date, period_label
        )
    except Exception as e:
        error = e
        import traceback
        print(f"[FAILED] Vocab Review 실행 실패: {e}")
        traceback.print_exc()

    # ── Run Log 탭 (성공/실패 무관, flag 0건이어도 반드시 남김) ─────────────
    try:
        if ss is None:
            ss = _open_spreadsheet()
        runlog_ws, _ = _get_or_create_tab(ss, RUNLOG_TAB, RUNLOG_HEADER)
        if error is None:
            log_row = [run_date, period_label, scanned, carved, weak, strong,
                       seed_only, ", ".join(SEED_WORDS)]
        else:
            log_row = [run_date, period_label, "FAILED", "-", "-", "-", "-",
                       f"ERROR: {type(error).__name__}: {str(error)[:200]}"]
        runlog_ws.append_row(log_row, value_input_option="RAW")
        print(f"[OK] Run Log 기록 — {'FAILED 행' if error else '시드 스냅샷: ' + ', '.join(SEED_WORDS)}")
    except Exception as e2:
        print(f"[FATAL] Run Log 기록 불가 — 시트 접근 자체가 실패: {e2}")
        sys.exit(1)

    if error is not None:
        sys.exit(1)


def _scan_and_record(
    ss: gspread.Spreadsheet, date_match, run_date: str, period_label: str
) -> tuple[int, int, int, int, int]:
    """원본 스캔 + Vocab Review 탭 기록. 실패는 위로 전파(호출자가 FAILED 처리)."""
    src = ss.sheet1  # 원본 기사 시트 — 읽기 전용
    rows = src.get_all_values()
    if not rows or rows[0][0] != SHEET_COLUMNS[0]:
        raise ValueError("원본 시트 헤더가 예상과 다릅니다 — 컬럼 구조 확인 필요")

    scanned = carved = weak = strong = seed_only = 0
    review_rows: list[list] = []
    src_gid = src.id

    for idx, row in enumerate(rows[1:], start=2):  # 시트 행번호 (헤더=1행)
        if len(row) <= _COL_TEXT or not date_match(row[_COL_DATE]):
            continue
        text = row[_COL_TEXT]
        if not text.strip():
            continue
        level = row[_COL_LEVEL]
        section = row[_COL_SECTION]
        sub_level = row[_COL_SUBLEVEL] if len(row) > _COL_SUBLEVEL else ""
        level_key = _level_key(level, sub_level)

        scanned += 1
        r = vocab_monitor.check(
            text, baseline_pct=BASELINE_PCT, section=section, level_key=level_key
        )
        art_type = classify(text, level_key).article_type.value

        if r.seed_carved_out:
            carved += 1
        if r.flag == vocab_monitor.VocabFlag.NONE:
            continue
        if r.flag == vocab_monitor.VocabFlag.WEAK:
            weak += 1
        else:
            strong += 1
        if (r.seed_hit_count > 0 and not r.seed_carved_out
                and not (r.above_baseline and r.not_word_hits)):
            seed_only += 1

        locate = (
            f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}'
            f'#gid={src_gid}&range=A{idx}", "{src.title}!A{idx}")'
        )
        review_rows.append([
            run_date, period_label, row[_COL_DATE], row[_COL_TOPIC],
            f"{level}/{sub_level or '?'}", section, art_type,
            r.flag.value, r.flag_reason, _axes(r), locate, "", "",
        ])

    # ── 콘솔 출력 (탭 쓰기 실패해도 결과는 여기서 보임) ─────────────────────
    print(f"\n스캔 {scanned}건 / carve-out {carved}건 / WEAK {weak} / STRONG {strong} / SEED_DRIFT 단독 {seed_only}")
    for r_ in review_rows:
        print(f"  [{r_[7]}] {r_[2]} | {r_[4]} | {r_[5]} | {r_[3][:40]}")
        print(f"      {r_[8]}  (축: {r_[9]})")
    if not review_rows:
        print("  flag 0건 — Vocab Review 탭에 추가할 행 없음")

    # ── Vocab Review 탭 (행 기록 실패는 위로 전파 → FAILED 처리) ────────────
    review_ws, _ = _get_or_create_tab(
        ss, REVIEW_TAB, REVIEW_HEADER, guide=vocab_monitor.REVIEW_GUIDE
    )
    if review_rows:
        start = len(review_ws.get_all_values()) + 1
        review_ws.update(
            values=review_rows, range_name=f"A{start}",
            value_input_option="USER_ENTERED",  # HYPERLINK 수식 해석
        )
        # 리뷰 액션 드롭다운 (외관용 — 실패해도 행 기록은 유지)
        try:
            from gspread.utils import ValidationConditionType
            col = REVIEW_HEADER.index("리뷰 액션") + 1
            col_a1 = gspread.utils.rowcol_to_a1(1, col)[:-1]
            review_ws.add_validation(
                f"{col_a1}{start}:{col_a1}{start + len(review_rows) - 1}",
                ValidationConditionType.one_of_list, REVIEW_ACTIONS,
                showCustomUi=True,
            )
        except Exception as e:
            print(f"[경고] 리뷰 액션 드롭다운 설정 실패 (행 기록은 완료): {e}")
    print(f"\n[OK] Vocab Review 탭 — {len(review_rows)}행 기록")
    return scanned, carved, weak, strong, seed_only


if __name__ == "__main__":
    main()
