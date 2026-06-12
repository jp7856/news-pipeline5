# NE Times Content Pipeline v4 — 핸드오프 문서

## 프로젝트 개요

영어 교육 신문(NE Times Kinder/Kids/Junior/Times/Junior M) 콘텐츠 자동 생성 파이프라인.
토픽 입력 → 기사 초안(표절 통과까지 자동 재작성) → AI 대화 수정 → 전체 제작 → 검수 → 발행 → 공개 사이트 게시.
**에이전트 구성의 단일 기준은 ORCHESTRATION.md** — 에이전트 1은 신문별 1-1~1-5로 분리됨.

## 레포 & 배포

- **v4 GitHub**: https://github.com/jp7856/news-pipeline4
- **v4 Railway**: https://web-production-8adb9.up.railway.app
- **v3 (동결, 태그 v3-final)**: https://github.com/jp7856/news-pipeline3 / https://web-production-d0e54.up.railway.app
- **발행 사이트**: https://jp7856.github.io/ne-times-site/ (레포: jp7856/ne-times-site, API_BASE = v4 ✅)
- 스택: Python 3.13, Flask + Flask-SocketIO, Claude Sonnet 4.6, Railway 자동 배포, GitHub Pages

## 파이프라인 흐름 (v4 시작 시점)

```
Generate → 레벨로 에이전트 1-1~1-5 라우팅 (create_agent1, 지침: agents/guidelines/*.md)
         → [Phase 1] SourceFinder(웹검색, 도메인 화이트리스트)
         → Writer → Plagiarism (실패 시 실패 항목 피드백으로 최대 3회 재작성)
         → 초안 미리보기 + 대화형 AI 수정/질문 (Reviser 채팅, 수정 시 표절 재검사)
         → [이후 작업 진행] → [Phase 2] Editor(자동반영) → Crossword + Workbook
         → Translator → ImageFinder → Reviewer(검수, 거부 시 fix_targets만 재작성 후 재검수 최대 2회)
         → Worksheet(시트 저장 — 통과 '작성완료' / 최종 거부 '검수거부' / 검수 실패 '검수오류')
         → [발행하기] → 시트 상태 '발행완료' → /api/published → 발행 사이트 노출
중단: Running 배지 클릭 (단계 사이 PipelineCancelled)
```

## v3까지 완성된 기능 전체

1. Agent 1~5 전체 파이프라인 (작성/번역/이미지/시트/검수)
2. 2단계 생성 (Phase 1 미리보기 → Phase 2 완성)
3. 대화형 AI 수정 (Reviser) — 수정 지시 + 질문 응답, 채팅 UI, 표절 컨텍스트, 6턴 기록
4. 표절 자동 재작성 루프 (최대 3회, 실패 항목 구체적 피드백) ← v4 초기 추가
5. AI 수정 후 표절 재검사 ← v4 초기 추가
6. 출처: Claude 웹 검색 (ALLOWED_DOMAINS 화이트리스트, 한국어 토픽 영어 번역 검색)
7. 교정 자동 반영, 번역 마커 방식, 이미지 폴백 체인
8. 히스토리 영구 저장 (구글 시트 로드), 발행 기능 (상태 컬럼)
9. 비용 추적 (usage_tracker, 로그 마지막 줄 Cost)
10. 중단 기능, /api/health 환경변수 점검

## 핵심 파일

```
ORCHESTRATION.md           # 에이전트 구성·지침 작성 규칙의 단일 기준
orchestrator.py            # run_phase1/run_phase2, PipelineCancelled
agents/level_agents.py     # 에이전트 1-1(KINDER)~1-5(JUNIOR M) + create_agent1 팩토리
agents/guidelines/         # 신문별 작성 지침 (Writer 프롬프트 주입) — 4개 매체 실측 CEFR 기준 입고, JUNIOR M만 placeholder
agents/content_producer.py # 에이전트 1 공통 베이스 — produce_article(표절 3회 루프) / produce_extras
agents/sub_agents/
  source_finder.py         # 웹 검색 출처 (BBC/Reuters 등은 크롤러 차단 — 넣으면 400)
  reviser.py               # (article, reply, changed) 반환
  usage_tracker.py         # TrackedClient — 모든 클라이언트는 이걸로 생성
dashboard/app.py           # /api/run /stop /continue /revise /publish /published /health
dashboard/templates/index.html  # 9탭 + continue-bar(채팅) + 발행 버튼
```

## Railway 환경변수 (v4 설정 완료)

- ANTHROPIC_API_KEY ✅
- GOOGLE_SHEETS_CREDENTIALS_JSON ✅ (JSON 내용 전체)
- GOOGLE_SHEET_ID ✅ = 1jA2lU16ImpYq1JxVl3hRLLLZn8cDGL6EKfnsQREsYQE (v3와 공유 중!)
- UNSPLASH_ACCESS_KEY ⚪ (미설정, 코드 기본값)
- 점검: GET /api/health

## 주의사항 (재발 방지)

- Google CSE는 신규 고객 폐쇄 — 다시 시도하지 말 것
- BBC/Reuters/Guardian/NYT/AP는 allowed_domains에 넣으면 400
- Railway 변수 수정 후 반드시 Deploy(Apply changes) 클릭
- 구글 서비스 계정 키는 "키 추가→새 키 만들기"로만 발급됨 (재다운로드 불가)
- 시트는 v3와 v4가 같은 것을 공유 중 — 분리 필요 시 새 시트 + 서비스 계정 공유 + SHEET_ID 교체

## 비용 (실측)

- 기사 1건: 약 $0.17~0.24 (240원, 표절 재작성 1회 포함)
- 표절 재작성 1회당 +약 50원 (최대 3회)
- AI 수정/질문 1회: 약 $0.02

## v4 후보 과제 (v3에서 이월)

- [x] 검수 거부 시 자동 재작성 + 시트 저장 순서 — 검수가 저장보다 먼저 실행되도록 변경.
      Reviewer가 거부 시 fix_targets(article/translation/crossword/workbook) 반환,
      대상만 재생성(기사 수정 시 표절 재검사 + 번역 자동 갱신) 후 재검수 최대 2회.
      최종 거부돼도 저장은 하되 상태 '검수거부'로 구분 (검수 API 오류는 '검수오류').
      테스트: tests/test_review_loop.py (2026-06-12)
- [ ] 배치 생성 (여러 기사 동시)
- [x] 누적 사용액 표시 — 시트 17번째 '비용(원)' 컬럼(Q열), 저장 시점(=검수 후, 최종) 비용 기록,
      /api/usage, 헤더 누적 배지, 히스토리 건별 비용. 구버전 행은 비용 미기록(0원 집계).
      v3는 A~P만 사용하므로 공유 시트 호환 (2026-06-12)
- [x] 발행 사이트 API_BASE를 v4로 전환 + Junior M 탭 (ne-times-site 4416c66, 2026-06-12)
      — v3는 서버 시작 후 발행분이 반영 안 되던 문제도 함께 해소
- [ ] "가장 어려운 단계" — 사용자가 정의 예정

---
마지막 수정: 2026-06-12 (누적 사용액 + 검수 재작성 루프·저장 순서 완료)
