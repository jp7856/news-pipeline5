import os
from dotenv import load_dotenv

load_dotenv(override=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"

GOOGLE_SHEETS_CREDENTIALS_JSON = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON", "credentials.json")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY", "")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "VLRkU7wWplDXzMjkBFFqvhVrR_orC10qFcHOApNkrTc")

MAX_ARTICLES_PER_RUN = int(os.getenv("MAX_ARTICLES_PER_RUN", "10"))

# ------------------------------------------------------------------
# 오케스트레이터 시스템 페르소나 (모든 서브에이전트 공유 — 프롬프트 캐싱)
# ------------------------------------------------------------------
SYSTEM_PROMPT = """You are a writer and editor of an English education for children and teens. \
You work on four weekly newspapers that are catered to different age and level of students \
who are studying English as a foreign language. \
The lowest is called NE Times Kinder and it is for kindergarteners and early elementary school \
students, and the language level is at CEFR level of A1 or lower. \
The next newspaper is called NE Times Kids and it is for elementary school students studying \
at a CEFR level of around A2 or A1-A2. \
The third newspaper is called NE Times Junior and it is for high elementary and low middle school \
students, and the CEFR level is around A2 or A2-B1. \
The highest is NE Times for high schoolers, and the CEFR level is around B1 or B1-B2.

You have worked in this field for about 15 years, making you highly experienced at both writing \
and editing articles, making suitable workbook activities, as well as choosing appropriate topics. \
You see the value in making English articles and content in that they can be helpful to students \
in increasing English skills, expanding knowledge about the world, indirectly experiencing how \
concepts are explained in English, and being exposed to a variety of information and perspectives."""

# ------------------------------------------------------------------
# 레벨별 신문 설정
# ------------------------------------------------------------------
# 수치 기준: 2026-06 실제 NE Times 4개 매체 CEFR 분석 (상세 표는 agents/guidelines/*.md).
# 각 매체는 내부에 L1~L3 서브레벨이 있고, 생성 기본 타깃은 중간인 L2.
LEVEL_CONFIG: dict[str, dict] = {
    "kinder": {
        "newspaper":        "NE Times Kinder",
        "cefr":             "A1 (media range Pre-A1 to A1)",
        "target":           "kindergarteners and early elementary school students (ages 5–8)",
        "word_count_range": "45–90",
        "paragraph_count":  "4–6",
    },
    "kids": {
        "newspaper":        "NE Times Kids",
        "cefr":             "A2 (media range A1+ to A2+)",
        "target":           "elementary school students (ages 9–12)",
        "word_count_range": "70–120",
        "paragraph_count":  "4–5",
    },
    "junior": {
        "newspaper":        "NE Times Junior",
        "cefr":             "early B1 (media range A2+ to B1)",
        "target":           "high elementary and low middle school students (ages 11–14)",
        "word_count_range": "150–190",
        "paragraph_count":  "4–5",
    },
    "times": {
        "newspaper":        "NE Times",
        "cefr":             "B1+ (media range B1 to B2)",
        "target":           "high school students (ages 15–18)",
        "word_count_range": "245–300",
        "paragraph_count":  "5–8",
    },
    # ⚠️ placeholder — junior 복사본. 실측 분석에 미포함, 에이전트 1-5 지침 입고 시 확정 필요
    "junior_m": {
        "newspaper":        "NE Times Junior M",
        "cefr":             "early B1 (media range A2+ to B1)",
        "target":           "high elementary and low middle school students (ages 11–14)",
        "word_count_range": "150–190",
        "paragraph_count":  "4–5",
    },
}

# ------------------------------------------------------------------
# 매체 내부 서브레벨 — 2026-06 실제 발행 기사 CSV 분석 (산문 기사만, 각주 제외).
# 평균이 아닌 실측 범위(min–max) 기준 — 기사는 반드시 이 범위 안에서 작성.
# 선택된 서브레벨 값이 LEVEL_CONFIG 위에 덮어써져 Writer 프롬프트에 들어간다.
# 상세 분석·문체 규칙: agents/guidelines/*.md / 분석 도구: tests/analyze_media_csv.py
# ------------------------------------------------------------------
DEFAULT_SUBLEVEL = "L2"

SUBLEVEL_CONFIG: dict[str, dict[str, dict]] = {
    "kinder": {  # KINDER는 L1~L2만 존재
        "L1": {"cefr": "Pre-A1", "word_count_range": "35–55",   "sentence_length": "4–6 words",   "paragraph_count": "4–5"},
        "L2": {"cefr": "A1",     "word_count_range": "45–90",   "sentence_length": "5–8 words",   "paragraph_count": "4–6"},
    },
    "kids": {
        "L1": {"cefr": "A1+",    "word_count_range": "55–70",   "sentence_length": "7–10 words",  "paragraph_count": "3–4"},
        "L2": {"cefr": "A2",     "word_count_range": "70–120",  "sentence_length": "8–12 words",  "paragraph_count": "4–5"},
        "L3": {"cefr": "A2+",    "word_count_range": "155–180", "sentence_length": "9–13 words",  "paragraph_count": "9–11"},
    },
    "junior": {
        "L1": {"cefr": "A2+",      "word_count_range": "115–160", "sentence_length": "10–15 words", "paragraph_count": "4"},
        "L2": {"cefr": "early B1", "word_count_range": "150–190", "sentence_length": "11–17 words", "paragraph_count": "4–5"},
        "L3": {"cefr": "B1",       "word_count_range": "190–230", "sentence_length": "13–18 words", "paragraph_count": "6–7"},
    },
    "times": {
        "L1": {"cefr": "B1",  "word_count_range": "110–150", "sentence_length": "13–18 words", "paragraph_count": "3–5"},
        "L2": {"cefr": "B1+", "word_count_range": "245–300", "sentence_length": "14–20 words", "paragraph_count": "5–8"},
        "L3": {"cefr": "B2",  "word_count_range": "255–300", "sentence_length": "15–19 words", "paragraph_count": "6–10"},
    },
    # ⚠️ placeholder — junior 복사본 (실측 분석 미포함)
    "junior_m": {
        "L1": {"cefr": "A2+",      "word_count_range": "115–160", "sentence_length": "10–15 words", "paragraph_count": "4"},
        "L2": {"cefr": "early B1", "word_count_range": "150–190", "sentence_length": "11–17 words", "paragraph_count": "4–5"},
        "L3": {"cefr": "B1",       "word_count_range": "190–230", "sentence_length": "13–18 words", "paragraph_count": "6–7"},
    },
}

# ------------------------------------------------------------------
# Google Sheets 컬럼 순서
# ------------------------------------------------------------------
SHEET_COLUMNS = [
    "ID", "생성일시", "레벨", "섹션", "토픽",
    "기사본문", "어휘", "출처",
    "표절검사통과", "수정제안수",
    "크로스워드생성수", "워크북세트수", "상태",
]
