"""Agent 4: Google Sheets 저장 — ContentPackage를 스프레드시트에 기록한다."""

import json
import logging
import os
from typing import Callable

import gspread
from google.oauth2.service_account import Credentials

from config import GOOGLE_SHEETS_CREDENTIALS_JSON, GOOGLE_SHEET_ID
from models import ArticleStatus, ContentPackage

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_COLUMNS = [
    "생성일시", "레벨", "섹션", "토픽", "단어수",
    "기사(영문)", "기사(한국어)", "요약(한국어)",
    "어휘", "출처", "표절검사", "이미지URL",
    "크로스워드", "워크북Set1", "워크북Set2", "상태", "비용(원)", "서브레벨",
    "검수경고",  # Agent5 LLM 지적사항 (soft — 상태와 무관, 발행 전 참고)
    "거부사유",  # hard 게이트 거부 시 게이트별 줄바꿈 구분 ("❌ [게이트] 측정값 / 허용 — 출처")
    "필자",      # On Air 캐릭터 바이라인 (BYLINE_AUTHORS — docs/on_air_bible.md 단일 소스)
]

# On Air 캐릭터 바이라인 — 발행물→필자 고정 매핑.
# IP 원본은 docs/on_air_bible.md. 사이트 바이라인·프로필 등 후속 작업도 이 상수를 참조한다.
BYLINE_AUTHORS: dict[str, str] = {
    "kinder":   "Leo",
    "kids":     "Ruby",
    "junior":   "Sunny",
    "junior_m": "Erin",
    "times":    "Daniel",
}

STATUS_COL = SHEET_COLUMNS.index("상태") + 1     # 상태 컬럼 위치 (1-based)
COST_COL = SHEET_COLUMNS.index("비용(원)") + 1   # 비용 컬럼 위치 (1-based)


class WorksheetAgent:
    def __init__(self, log_callback: Callable[[str], None] | None = None):
        self._log = log_callback or (lambda msg: logger.info(msg))
        self._sheet = None
        self.last_row: int | None = None  # 마지막으로 저장한 행 번호 (발행용)

    def run(self, package: ContentPackage, cost_krw: int | None = None) -> tuple[ContentPackage, str]:
        """
        ContentPackage를 Google Sheets에 저장한다.
        Returns: (package, sheet_url)
        """
        self._log("[Agent4] Google Sheets 저장 시작")
        sheet_url = ""
        try:
            sheet = self._get_sheet()
            self._ensure_header(sheet)
            row = self._package_to_row(package, cost_krw)
            resp = sheet.append_row(row, value_input_option="USER_ENTERED")
            self.last_row = self._parse_row_number(resp)
            sheet_url = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}"
            self._log(f"[Agent4] 저장 완료 → {sheet_url}")
        except Exception as e:
            self._log(f"[Agent4] 저장 오류: {e}")
        return package, sheet_url

    def mark_published(self, row: int) -> bool:
        """해당 행의 상태를 '발행완료'로 변경한다."""
        from datetime import datetime
        try:
            sheet = self._get_sheet()
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            sheet.update_cell(row, STATUS_COL, f"발행완료 ({stamp})")
            self._log(f"[Publish] {row}행 발행 완료")
            return True
        except Exception as e:
            self._log(f"[Publish] 발행 처리 오류: {e}")
            return False

    @staticmethod
    def _parse_row_number(append_response) -> int | None:
        """append_row 응답에서 행 번호를 추출한다. 예: 'Sheet1!A12:P12' → 12"""
        try:
            rng = append_response["updates"]["updatedRange"]
            import re
            m = re.search(r"!\w?[A-Z]+(\d+):", rng)
            return int(m.group(1)) if m else None
        except (KeyError, TypeError, AttributeError):
            return None

    # ------------------------------------------------------------------

    def _get_sheet(self) -> gspread.Worksheet:
        if self._sheet is not None:
            return self._sheet

        # Railway env var는 JSON 문자열, 로컬은 파일 경로 둘 다 지원
        creds_val = GOOGLE_SHEETS_CREDENTIALS_JSON
        try:
            creds_dict = json.loads(creds_val)
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        except (json.JSONDecodeError, TypeError):
            # 파일 경로로 시도
            creds = Credentials.from_service_account_file(creds_val, scopes=SCOPES)

        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(GOOGLE_SHEET_ID)
        self._sheet = spreadsheet.sheet1
        return self._sheet

    def load_history(self) -> list[dict]:
        """시트 전체 행을 읽어 대시보드 히스토리 형식으로 반환한다."""
        try:
            sheet = self._get_sheet()
            rows = sheet.get_all_values()
            # 헤더 첫 컬럼만 확인 (상태 컬럼 추가 전 구버전 헤더와도 호환)
            if not rows or not rows[0] or rows[0][0] != SHEET_COLUMNS[0]:
                return []

            sheet_url = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}"
            history = []
            for idx, row in enumerate(rows[1:]):  # 헤더 제외
                if len(row) < 12:
                    continue
                try:
                    crossword = json.loads(row[12]) if row[12] else []
                    wb1 = json.loads(row[13]) if len(row) > 13 and row[13] else {}
                    wb2 = json.loads(row[14]) if len(row) > 14 and row[14] else {}
                except (json.JSONDecodeError, IndexError):
                    crossword, wb1, wb2 = [], {}, {}

                result = {
                    "topic": row[3],
                    "level": row[1],
                    "section": row[2],
                    "sub_level": row[17] if len(row) > 17 else "",  # 구버전 행은 미기록
                    "article": {
                        "text": row[5],
                        "text_ko": row[6],
                        "summary_ko": row[7],
                        "word_count": int(row[4]) if row[4].isdigit() else 0,
                        "vocabulary": [v.strip() for v in row[8].split(",") if v.strip()],
                        "sources": [s for s in row[9].split("\n") if s.strip()],
                    },
                    "plagiarism": {
                        "passed": row[10] == "PASS",
                        "checklist": {},
                        "notes": "",
                    },
                    "editing": [],
                    "crossword": crossword,
                    "workbook": [
                        {**wb1, "set_number": 1} if wb1 else {},
                        {**wb2, "set_number": 2} if wb2 else {},
                    ],
                    "image_url": row[11],
                    "sheet_url": sheet_url,
                    "review": (
                        {"passed": False, "status": "검수거부",
                         "notes": (row[19] if len(row) > 19 and row[19] else "시트 기록: 검수 거부"),
                         "warnings": row[18] if len(row) > 18 else ""}
                        if len(row) > 15 and row[15].startswith("검수거부")
                        else (
                            {"passed": True, "status": "작성완료", "notes": "",
                             "warnings": row[18]}
                            if len(row) > 18 and row[18] else None
                        )
                    ),
                    "sheet_row": idx + 2,  # 헤더가 1행이므로 데이터는 2행부터
                    "published": len(row) > 15 and row[15].startswith("발행"),
                }
                try:
                    cost_krw = round(float(row[16])) if len(row) > 16 and row[16] else 0
                except ValueError:
                    cost_krw = 0
                history.append({
                    "idx": idx,
                    "created_at": row[0],
                    "topic": row[3],
                    "level": row[1],
                    "section": row[2],
                    "cost_krw": cost_krw,
                    "result": result,
                })
            logger.info(f"[Worksheet] 히스토리 {len(history)}건 로드")
            return history
        except Exception as e:
            logger.warning(f"[Worksheet] 히스토리 로드 실패 (무시): {e}")
            return []

    def _ensure_header(self, sheet: gspread.Worksheet) -> None:
        first_row = sheet.row_values(1)
        if not first_row:
            sheet.insert_row(SHEET_COLUMNS, index=1)
        elif first_row != SHEET_COLUMNS:
            # 컬럼이 추가된 경우 헤더를 제자리에서 갱신 (기존 데이터 유지)
            sheet.update(values=[SHEET_COLUMNS], range_name="A1")

    def _package_to_row(self, pkg: ContentPackage, cost_krw: int | None = None) -> list:
        from datetime import datetime

        crossword = json.dumps(
            [{"word": c.word, "ko": c.korean_definition,
              "b1": c.sentence_b1, "b1b2": c.sentence_b1_b2}
             for c in pkg.crossword_sentences],
            ensure_ascii=False
        )

        def wb_json(ws):
            return json.dumps({
                "vocab": ws.vocabulary_activity,
                "true_false": ws.true_false,
                "comprehension": ws.comprehension_questions,
                "discussion": ws.discussion_questions,
            }, ensure_ascii=False)

        wb1 = wb_json(pkg.workbook_sets[0]) if len(pkg.workbook_sets) > 0 else ""
        wb2 = wb_json(pkg.workbook_sets[1]) if len(pkg.workbook_sets) > 1 else ""

        return [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            pkg.level.value,
            pkg.section.value,
            pkg.topic,
            pkg.article.word_count,
            pkg.article.text,
            pkg.article.text_ko,
            pkg.article.summary_ko,
            ", ".join(pkg.article.vocabulary),
            "\n".join(pkg.article.sources),
            "PASS" if pkg.plagiarism_report.passed else "WARNING",
            pkg.image_url,
            crossword,
            wb1,
            wb2,
            self._status_label(pkg),
            cost_krw if cost_krw is not None else "",
            pkg.sub_level,
            (f"⚠ Agent5 지적사항: {pkg.review_result.warnings}"
             if pkg.review_result and pkg.review_result.warnings else ""),
            (pkg.review_result.notes
             if pkg.review_result and not pkg.review_result.passed else ""),
            BYLINE_AUTHORS.get(pkg.level.value, ""),
        ]

    @staticmethod
    def _status_label(pkg: ContentPackage) -> str:
        review = pkg.review_result
        if review is None or review.passed:
            return "작성완료"
        if review.status == ArticleStatus.ERROR:
            return "검수오류"  # 검수 자체가 실패한 경우 — 콘텐츠 품질 거부와 구분
        return "검수거부"
