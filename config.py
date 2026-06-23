import os
from dotenv import load_dotenv

load_dotenv(override=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_MODEL_FAST = "claude-haiku-4-5-20251001"  # 단순 판정용 (표절·사실검사)

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
# 수치 기준: 2026-06 실제 NE Times 5개 매체 전수 분석 (basic.xlsx, 산문 기사 248건).
# 분석 도구: tests/analyze_basic_xlsx.py / 설계 원칙: 매체 간 겹침 최소화 + 실측 범위 내 강제.
# 매체 간 핵심 변별축 = CEFR + 평균 문장 길이 (단어 수는 중간 구간에서 일부 겹침 — 지침 참조).
# 각 매체는 내부에 L1~L3 서브레벨이 있고(JUNIOR M은 L1~L2), 생성 기본 타깃은 L2.
LEVEL_CONFIG: dict[str, dict] = {
    "kinder": {
        "newspaper":        "NE Times Kinder",
        "cefr":             "Pre-A1 to A1",
        "target":           "kindergarteners and early elementary school students (ages 5–8)",
        "word_count_range": "40–90",
        "paragraph_count":  "4–6",
    },
    "kids": {
        "newspaper":        "NE Times Kids",
        "cefr":             "A1+ to A2",
        "target":           "elementary school students (ages 8–11)",
        "word_count_range": "60–180",
        "paragraph_count":  "3–11",
    },
    "junior": {
        "newspaper":        "NE Times Junior",
        "cefr":             "A2+ to B1",
        "target":           "upper elementary students (ages 11–13)",
        "word_count_range": "115–230",
        "paragraph_count":  "4–7",
    },
    "junior_m": {
        "newspaper":        "NE Times Junior M",
        "cefr":             "B1 to B1+",
        "target":           "middle school students (ages 13–16)",
        "word_count_range": "150–215",
        "paragraph_count":  "5–8",
    },
    "times": {
        "newspaper":        "NE Times",
        "cefr":             "B1 to B2",
        "target":           "high school students (ages 16–18)",
        "word_count_range": "110–310",
        "paragraph_count":  "3–10",
    },
}

# ------------------------------------------------------------------
# 매체 내부 서브레벨 — 2026-06 basic.xlsx 전수 분석 (산문 기사만, 각주·한글 뜻풀이 제외).
# 실측 분포의 코어(p5~p95)를 라운드 처리한 값 — 기사는 반드시 이 범위 안에서 작성.
# 선택된 서브레벨 값이 LEVEL_CONFIG 위에 덮어써져 Writer 프롬프트에 들어간다.
# 상세 분석·문체 규칙: agents/guidelines/*.md / 분석 도구: tests/analyze_basic_xlsx.py
# 매체 간 단어 수는 중간 구간(JUNIOR/JUNIOR M/TIMES L1)에서 겹침 — CEFR·문장 길이로 변별.
# ------------------------------------------------------------------
DEFAULT_SUBLEVEL = "L2"

SUBLEVEL_CONFIG: dict[str, dict[str, dict]] = {
    "kinder": {  # KINDER는 L1~L2만 존재
        "L1": {"cefr": "Pre-A1", "word_count_range": "40–55",   "sentence_length": "4–6 words",   "paragraph_count": "4–5"},
        "L2": {"cefr": "A1",     "word_count_range": "55–90",   "sentence_length": "5–8 words",   "paragraph_count": "4–6"},
    },
    "kids": {
        # L2 = 표준 뉴스(71–103 클러스터). 128–168 기획(Close Up/People&Places)은 별도 포맷이라 L2 기본 생성에서 제외.
        "L1": {"cefr": "A1+", "word_count_range": "60–75",   "sentence_length": "7–10 words",  "paragraph_count": "3–4"},
        "L2": {"cefr": "A2",  "word_count_range": "75–105",  "sentence_length": "8–12 words",  "paragraph_count": "4–6"},
        # L3은 L2와 난이도(A2) 동일 — 길이·포맷("What's Hot" 3항목)으로만 구분.
        "L3": {"cefr": "A2",  "word_count_range": "130–180", "sentence_length": "9–12 words",  "paragraph_count": "8–11"},
    },
    "junior": {
        "L1": {"cefr": "A2+", "word_count_range": "115–150", "sentence_length": "10–14 words", "paragraph_count": "4"},
        "L2": {"cefr": "B1",  "word_count_range": "150–190", "sentence_length": "12–16 words", "paragraph_count": "4–5"},
        # L3은 L2와 난이도(B1) 동일 — 소제목·구체 내용이라 더 길 뿐 더 어렵진 않음.
        "L3": {"cefr": "B1",  "word_count_range": "190–230", "sentence_length": "14–18 words", "paragraph_count": "6–7"},
    },
    "junior_m": {  # 유일한 월간지(중학생·시사/이슈 중심) — L1~L2만 존재. JUNIOR와 길이 겹침 정상.
        "L1": {"cefr": "B1",  "word_count_range": "150–185", "sentence_length": "11–15 words", "paragraph_count": "5–7"},
        "L2": {"cefr": "B1+", "word_count_range": "185–215", "sentence_length": "12–16 words", "paragraph_count": "6–8"},
    },
    "times": {
        # L1 = 압축 뉴스(110–150). 60–80단어 Briefs는 생성 대상에서 제외(매체 변별 위해). 실측상 B1.
        "L1": {"cefr": "B1", "word_count_range": "110–150", "sentence_length": "13–18 words", "paragraph_count": "3–5"},
        # L2·L3은 길이(260–300)·난이도(B2) 사실상 동일 — L3은 문단 수↑·다관점 구조로 구분(VoA 장문은 이상치 제외).
        "L2": {"cefr": "B2", "word_count_range": "260–300", "sentence_length": "15–20 words", "paragraph_count": "5–8"},
        "L3": {"cefr": "B2", "word_count_range": "280–310", "sentence_length": "16–20 words", "paragraph_count": "7–10"},
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
