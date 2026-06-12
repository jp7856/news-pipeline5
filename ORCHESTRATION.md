# NE Times Content Pipeline v4 — 전체 오케스트레이션 정의서

이 문서는 파이프라인의 **에이전트 구성과 역할 분담의 단일 기준**입니다.
에이전트 1은 신문(레벨)별로 5개로 분리되어 있으며, 각자의 작성 지침은
`agents/guidelines/` 아래 마크다운 파일로 관리합니다 — **지침 수정에 코드 변경이 필요 없습니다.**

## 1. 전체 흐름

```
[대시보드] 토픽 + 레벨 + 섹션 선택 → Generate
    │
    ▼  레벨에 따라 에이전트 1-1 ~ 1-5 중 하나로 라우팅
┌─ Phase 1 ──────────────────────────────────────────────┐
│ SourceFinder(웹검색) → Writer(지침 마크다운 주입)        │
│   → Plagiarism (실패 시 최대 3회 재작성)                 │
│ → 초안 미리보기 + AI 채팅 수정/질문 (수정 시 표절 재검사)│
└────────────────────────────────────────────────────────┘
    │  [이후 작업 진행]
    ▼
┌─ Phase 2 ──────────────────────────────────────────────┐
│ Editor(교정 자동반영) → Crossword + Workbook            │
│ → 에이전트 2 Translator → 에이전트 3 ImageFinder        │
│ → 에이전트 5 Reviewer (거부 시 fix_targets만 재작성,    │
│   재검수 최대 2회)                                       │
│ → 에이전트 4 Worksheet (시트 저장 — 통과 '작성완료' /   │
│   최종 거부 '검수거부' / 검수 실패 '검수오류')           │
└────────────────────────────────────────────────────────┘
    │  [발행하기]
    ▼
시트 상태 '발행완료' → /api/published → 발행 사이트 게시
```

## 2. 에이전트 로스터

### 에이전트 1 — 콘텐츠 제작 (신문별 5개)

| 에이전트 | 레벨 코드 | 신문 | 지침 파일 |
|---|---|---|---|
| **에이전트 1-1** | `kinder` | NE Times Kinder (KINDER) | `agents/guidelines/agent1_1_kinder.md` |
| **에이전트 1-2** | `kids` | NE Times Kids (KIDS) | `agents/guidelines/agent1_2_kids.md` |
| **에이전트 1-3** | `junior` | NE Times Junior (JUNIOR) | `agents/guidelines/agent1_3_junior.md` |
| **에이전트 1-4** | `times` | NE Times (TIMES) | `agents/guidelines/agent1_4_times.md` |
| **에이전트 1-5** | `junior_m` | NE Times Junior M (JUNIOR M) | `agents/guidelines/agent1_5_junior_m.md` |

- 구현: `agents/level_agents.py` — 모두 `ContentProducerAgent`를 상속한 얇은 서브클래스.
  공통 파이프라인(출처 검색 → 작성 → 표절 루프 → 교정 → 크로스워드/워크북)은 동일하고,
  **자기 지침 마크다운을 읽어 Writer 프롬프트에 주입**하는 점만 다릅니다.
- 라우팅: `create_agent1(level)` 팩토리가 대시보드에서 선택된 레벨로 에이전트를 결정합니다.
- ⚠️ JUNIOR M(`junior_m`)은 신설 레벨 — 기본 사양(단어 수 등)이 현재 JUNIOR 값의
  복사본(placeholder)입니다. 지침 입고 시 `config.py LEVEL_CONFIG["junior_m"]`도 함께 확정 필요.

### 에이전트 2~5 (레벨 공통)

| 에이전트 | 역할 | 구현 |
|---|---|---|
| 에이전트 2 | 한국어 번역 (레벨별 번역 문체) | `agents/translator.py` |
| 에이전트 3 | 이미지 탐색 (폴백 체인) | `agents/image_finder.py` |
| 에이전트 4 | 구글 시트 저장 + 발행 상태 관리 | `agents/worksheet.py` |
| 에이전트 5 | 최종 검수 — 거부 시 fix_targets 반환 | `agents/reviewer.py` |

### 서브에이전트 (에이전트 1 내부)

| 서브에이전트 | 역할 |
|---|---|
| SourceFinder | Claude 웹 검색으로 실제 출처 확보 (도메인 화이트리스트) |
| Writer | 기사 작성 — **레벨 지침 마크다운이 여기에 주입됨** |
| PlagiarismChecker | 표절 검사 (실패 항목 피드백) |
| Editor | 교정 제안 + 자동 반영 |
| Crossword / Workbook | 부교재 생성 |
| Reviser | 대화형 수정 (Phase 1 채팅, 검수 거부 재작성에도 재사용) |

## 3. 지침 마크다운 작성 규칙

> **수치 기준**: 2026-06 실제 발행 기사 CSV 분석 (4개 매체, 산문 기사 155건,
> 각주 제외 — 분석 도구: `tests/analyze_media_csv.py`).
> 수치는 평균이 아닌 **실측 범위(min–max)** — 기사는 반드시 범위 안에서 작성합니다.
> 각 매체의 서브레벨(L1~L3, KINDER는 L1~L2)은 `config.py SUBLEVEL_CONFIG`에 정의
> (기본 L2). 선택된 서브레벨의 단어 수·문장 길이·CEFR이 LEVEL_CONFIG 위에 덮어써져
> Writer 프롬프트에 들어가고, 지침 파일에는 범위 표 + **문체 규칙**을 둡니다.
> 매체 경계는 연속적(KIDS L3 ≈ JUNIOR L1, JUNIOR L3 ≈ TIMES L1).
> JUNIOR M은 분석 미포함 — placeholder. 서브레벨은 시트 18번째 컬럼(R열)에 기록됩니다.

- 위치: `agents/guidelines/agent1_X_<level>.md` (위 표 참조)
- **HTML 주석(`<!-- -->`)을 제외한 파일 본문 전체가 Writer 프롬프트에
  "Newspaper-specific writing guidelines"로 그대로 주입됩니다.**
  - 본문이 비어 있으면(주석만 있으면) 주입하지 않고 기본 프롬프트만 사용합니다.
  - 한국어/영어 모두 사용 가능. 주입되길 원치 않는 메모는 HTML 주석으로.
- 단어 수·단락 수·CEFR 같은 구조 사양은 `config.py LEVEL_CONFIG`가 기준입니다.
  지침에서 다른 값을 지시하면 프롬프트 안에서 충돌하므로, 사양 변경은 LEVEL_CONFIG를 수정하세요.
- 지침에 담기 좋은 내용: 문체·톤, 단어/문법 허용 범위, 단락 구성 패턴, 제목 규칙,
  다뤄도 되는/안 되는 소재, 섹션별 변형, 좋은 기사·나쁜 기사 예시 등.

## 4. 핵심 파일 맵

```
ORCHESTRATION.md           # (이 문서) 오케스트레이션 단일 기준
orchestrator.py            # run_phase1/run_phase2 — create_agent1(level)로 라우팅
agents/level_agents.py     # 에이전트 1-1 ~ 1-5 정의 + create_agent1 팩토리
agents/content_producer.py # 에이전트 1 공통 파이프라인 (베이스 클래스)
agents/guidelines/         # 신문별 작성 지침 (사용자 관리 영역)
config.py                  # LEVEL_CONFIG — 레벨별 구조 사양 (단어수·CEFR·대상)
```

---
마지막 수정: 2026-06-12 (에이전트 1 → 1-1~1-5 분리)
