# NE Times Content Pipeline v5 — 핸드오프 문서

## 프로젝트 개요

영어 교육 신문(NE Times Kinder/Kids/Junior/Times/Junior M) 콘텐츠 자동 생성 파이프라인.
토픽 입력 → 기사 초안(표절 통과까지 자동 재작성) → AI 대화 수정 → 전체 제작 → 검수 → 발행 → 공개 사이트 게시.
**에이전트 구성의 단일 기준은 ORCHESTRATION.md** — 에이전트 1은 신문별 1-1~1-5로 분리됨.

## 레포 & 배포

- **v5 GitHub**: https://github.com/jp7856/news-pipeline5
- **v5 Railway**: https://web-production-0763d.up.railway.app
- **v4 (이전)**: https://github.com/jp7856/news-pipeline4 / https://web-production-8adb9.up.railway.app
- **발행 사이트 (현재)**: https://jp7856.github.io/ne-times-site5/ (레포: jp7856/ne-times-site5, Railway /api/published 호출)
- **구 발행 사이트 (연결 해제)**: https://jp7856.github.io/ne-times-site/ — 더 이상 업데이트 안 됨, 빈 화면
- 스택: Python 3.13, Flask + Flask-SocketIO, Claude Sonnet 4.6, Railway 자동 배포, GitHub Pages

## 파이프라인 흐름

```
Generate → 레벨로 에이전트 1-1~1-5 라우팅 (create_agent1, 지침: agents/guidelines/*.md)
         → [Phase 1] SourceFinder(웹검색, 도메인 화이트리스트, 최신 기사 우선·발행일 수집)
         → Writer → Plagiarism (실패 시 실패 항목 피드백으로 최대 3회 재작성, 걸린 항목 로그)
         → FactCheck (출처 대조 사실 점검 — 불일치 시 1회 재작성 + 표절 재검사)
         → 초안 미리보기 + 대화형 AI 수정/질문 (Reviser 채팅, 수정 시 표절 재검사)
         → [이후 작업 진행] → [Phase 2] Editor(자동반영) → Crossword + Workbook
         → Translator → ImageFinder(기존 이미지 제외 + 후보 중 선택 — 매체별 변별력)
         → Reviewer(검수, 거부 시 fix_targets만 재작성 후 재검수 최대 2회)
         → Worksheet(시트 저장 — 통과 '작성완료' / 최종 거부 '검수거부' / 검수 실패 '검수오류')
         → [발행하기] → 시트 상태 '발행완료' → /api/published → ne-times-site5 노출
중단: Running 배지 클릭 (단계 사이 PipelineCancelled)
```

## 구현 완료 기능 전체

1. Agent 1~5 전체 파이프라인 (작성/번역/이미지/시트/검수)
2. 2단계 생성 (Phase 1 미리보기 → Phase 2 완성)
3. 대화형 AI 수정 (Reviser) — 수정 지시 + 질문 응답, 채팅 UI, 표절 컨텍스트, 6턴 기록
4. 표절 자동 재작성 루프 (최대 3회, 실패 항목 구체적 피드백)
5. AI 수정 후 표절 재검사
6. 출처: Claude 웹 검색 (ALLOWED_DOMAINS 화이트리스트, 한국어 토픽 영어 번역 검색)
7. 교정 자동 반영, 번역 마커 방식, 이미지 폴백 체인
8. 히스토리 영구 저장 (구글 시트 로드), 발행 기능 (상태 컬럼)
9. 월별 누적 사용액 — 헤더 배지(이번달 NNN원·N건) + 클릭 시 가로 막대 그래프 모달
   - /api/usage: current_month_krw / monthly[] 반환, 매월 1일 자동 초기화
10. 발행 → ne-times-site5 노출 (GitHub 토큰 불필요, Railway API 직접 호출)
11. WebSocket 재연결 시 article_ready 유실 방지
    - sessionStorage 기반 지속 세션 ID → 재연결 후에도 같은 room에서 이벤트 수신
12. 중단 기능, /api/health 환경변수 점검

## 핵심 파일

```
ORCHESTRATION.md           # 에이전트 구성·지침 작성 규칙의 단일 기준
orchestrator.py            # run_phase1/run_phase2, PipelineCancelled
agents/level_agents.py     # 에이전트 1-1(KINDER)~1-5(JUNIOR M) + create_agent1 팩토리
agents/guidelines/         # 신문별 작성 지침 (Writer 프롬프트 주입) — 5개 매체 전부 basic.xlsx 전수 분석 기준 입고 (JUNIOR M 포함)
agents/content_producer.py # 에이전트 1 공통 베이스 — produce_article(표절 3회 루프) / produce_extras
agents/sub_agents/
  source_finder.py         # 웹 검색 출처 (BBC/Reuters 등은 크롤러 차단 — 넣으면 400)
  fact_checker.py          # 기사-출처 대조 사실 점검 (출처 없으면 생략)
  reviser.py               # (article, reply, changed) 반환
  usage_tracker.py         # TrackedClient — 모든 클라이언트는 이걸로 생성
dashboard/app.py           # Flask 앱
                           #   /api/run /stop /continue /revise — 파이프라인 제어
                           #   /api/publish — 시트 상태 '발행완료' 처리 (GitHub 토큰 불필요)
                           #   /api/published — 발행 기사 목록 (ne-times-site5 전용)
                           #   /api/usage — 월별 사용액 (current_month_krw, monthly[])
                           #   /api/history, /api/health
dashboard/templates/index.html  # 9탭 + continue-bar(채팅) + 발행 버튼 + 월별 사용액 그래프
```

## Railway 환경변수 (v5 — 신규 설정 필요)

- ANTHROPIC_API_KEY ⚠️ 설정 필요
- GOOGLE_SHEETS_CREDENTIALS_JSON ⚠️ 설정 필요 (JSON 내용 전체)
- GOOGLE_SHEET_ID ⚠️ 설정 필요 = v5 전용 새 시트 권장 (v4까지는 1jA2lU16...을 v3와 공유)
- UNSPLASH_ACCESS_KEY ⚪ (미설정 시 코드 기본값 사용)
- GITHUB_TOKEN — **불필요** (ne-times-site5는 Railway API 직접 호출)
- 점검: GET /api/health

## 주의사항 (재발 방지)

- Google CSE는 신규 고객 폐쇄 — 다시 시도하지 말 것
- BBC/Reuters/Guardian/NYT/AP/wired.com/popularmechanics.com는 allowed_domains에 넣으면 400 (Anthropic 크롤러 차단)
  - 차단 도메인이 목록에 단 하나라도 있으면 web_search 전체가 400 → 출처 0건
- ALLOWED_DOMAINS은 교육 적합 10개로 한정: 학생전용 7(timeforkids/dogonews/kidsnews.com.au/newsforkids/teachingkidsnews/youngzine/snexplores) + 신뢰최상위 3(nasa.gov/nationalgeographic/smithsonianmag)
- Railway 변수 수정 후 반드시 Deploy(Apply changes) 클릭
- 구글 서비스 계정 키는 "키 추가→새 키 만들기"로만 발급됨 (재다운로드 불가)
- 시트는 v3와 v4가 같은 것을 공유 중 — 분리 필요 시 새 시트 + 서비스 계정 공유 + SHEET_ID 교체
- ne-times-site5는 Railway /api/published를 직접 호출 — articles.json 정적 파일 방식 아님
- ne-times-site(구 사이트)는 의도적으로 연결 해제됨 — 복원하지 말 것
- ⚠ run_vocab_review.py / vocab_monitor.py / analytical_seed.py 등 어휘 리뷰 계열 수정 시:
  push 후 `railway up --service vocab-review-cron` 필요 (cron 서비스는 푸시 자동 배포 안 됨 — Railway 설계.
  branch trigger는 master로 연결돼 있으나 cron 스케줄 서비스에는 무효 — 2026-07-02 대조 실험으로 확인)

## 비용 (실측)

- 기사 1건: 약 $0.17~0.24 (240원, 표절 재작성 1회 포함)
- 표절 재작성 1회당 +약 50원 (최대 3회)
- AI 수정/질문 1회: 약 $0.02

## 잔여 과제 (v5 계속)

- [ ] 출처 0건 문제: Writer가 검색 결과 전부 부적합 판정 시 → 로그 확인 후 방향 결정
- [ ] 평균 문장 길이 코드 강제 여부 미정 (현재 프롬프트 지시만)
- [x] JUNIOR M(1-5): basic.xlsx 분석으로 확정 (L1~L2, B1~B1+, 중학생·시사/이슈 중심)
- [ ] 배치 생성 (여러 기사 동시)

## v5 이관 체크리스트

- [ ] Railway 환경변수 3종 설정 (ANTHROPIC_API_KEY / GOOGLE_SHEETS_CREDENTIALS_JSON / GOOGLE_SHEET_ID)
- [ ] v5 전용 구글 시트 생성 후 서비스 계정 공유 + SHEET_ID 교체
- [ ] ne-times-site5 레포에서 Railway URL을 `web-production-0763d.up.railway.app`으로 설정
- [ ] Railway Deploy(Apply changes) 클릭 후 /api/health 확인

---
마지막 수정: 2026-06-18 (v5 이관 — 레포·배포·발행 사이트 URL 업데이트)
