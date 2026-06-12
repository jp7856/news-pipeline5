# NE Times Content Pipeline v3 — 핸드오프 문서

## 프로젝트 개요

영어 교육 신문(NE Times Kinder/Kids/Junior/Times) 콘텐츠 자동 생성 파이프라인.
토픽 입력 → 기사 초안 → AI 대화 수정 → 전체 제작(교정·크로스워드·워크북·번역·이미지·시트) → 검수 → 발행 → 공개 사이트 게시.

## 레포 & 배포

- **v3 GitHub**: https://github.com/jp7856/news-pipeline3
- **v3 Railway**: https://web-production-d0e54.up.railway.app
- **발행 사이트**: https://jp7856.github.io/ne-times-site/ (레포: jp7856/ne-times-site)
- 스택: Python 3.13, Flask + Flask-SocketIO, Claude Sonnet 4.6, Railway 자동 배포, GitHub Pages

## v3에서 완성된 것 (v2 대비 추가)

1. **Agent 5 (Reviewer)** — ContentPackage 기반 최종 검수, 승인/거부 + 사유
2. **히스토리 영구 저장** — 앱 시작 시 구글 시트에서 자동 로드 (서버 재시작에도 유지)
3. **대시보드 검수 탭** — 9번째 탭, 승인/거부 카드 표시
4. **구글 시트 연동 실제 세팅** — 서비스 계정 news-repoter@ne-times-pipeline.iam.gserviceaccount.com
5. **출처 환각 해결** — Claude 웹 검색(web_search_20260209)으로 실제 기사 검색
   - 도메인 화이트리스트(교육용 뉴스 + NPR/NASA 등), 한국어 토픽은 영어 번역 후 검색
   - 주의: BBC/Reuters/Guardian/NYT/AP는 Anthropic 크롤러 차단으로 allowed_domains에 넣으면 400
   - 주의: Google CSE는 신규 고객 폐쇄로 사용 불가 (다시 시도하지 말 것)
6. **교정 자동 반영** — Editor 제안을 본문에 적용한 뒤 크로스워드/워크북/번역 생성
7. **번역 마커 방식** — JSON 대신 <번역></번역> 마커 (따옴표로 인한 잘림 해결)
8. **비용 추적** — usage_tracker.py(TrackedClient), 파이프라인 종료 시 실비용 로그
9. **2단계 생성** — Phase 1(출처+기사+표절) → 미리보기 → Phase 2(교정~검수)
10. **중단 기능** — Running 배지 클릭으로 단계 사이 중단 (PipelineCancelled)
11. **대화형 AI 수정 (Reviser)** — 초안에 수정 지시/질문 모두 처리, 채팅 UI,
    표절 검사 결과 컨텍스트 제공, 최근 6턴 대화 기록 유지
12. **발행 기능** — 발행 버튼 → 시트 상태 '발행완료' → /api/published → 발행 사이트 표시

## 파일 구조

```
news-pipeline3/
├── config.py              # API 키, LEVEL_CONFIG, SYSTEM_PROMPT
├── models.py              # Level, Section, ContentPackage, ReviewResult
├── orchestrator.py        # run_phase1/run_phase2/run, PipelineCancelled, 비용 요약
├── agents/
│   ├── content_producer.py    # produce_article(Phase1) / produce_extras(Phase2), cancel_check
│   ├── translator.py          # 마커 방식 번역 (max_tokens 8192)
│   ├── image_finder.py        # Unsplash, 폴백 체인(어휘2→어휘1→토픽→섹션)
│   ├── worksheet.py           # 시트 16컬럼(+상태), load_history, mark_published
│   ├── reviewer.py            # Agent 5 검수 (본문/요약 전체 전달)
│   └── sub_agents/
│       ├── source_finder.py   # Claude 웹 검색 출처 (ALLOWED_DOMAINS)
│       ├── reviser.py         # 대화형 초안 수정/질문 응답 → (article, reply, changed)
│       ├── usage_tracker.py   # TrackedClient, reset_usage/usage_summary
│       ├── writer.py          # real_sources 주입, AI의 URL 생성 금지
│       └── editor/crossword/workbook/plagiarism_checker/utils.py
└── dashboard/
    ├── app.py                 # /api/run /stop /continue /revise /publish /published /history
    └── templates/index.html   # 9탭, 중단 배지, continue-bar(채팅 UI), 발행 버튼
```

## 파이프라인 흐름

```
Generate → [Phase 1] SourceFinder(웹검색) → Writer → Plagiarism(실패 시 재작성 1회)
         → 초안 미리보기 + 대화형 수정/질문 (Reviser, 반복 가능)
         → [이후 작업 진행] → [Phase 2] Editor(자동반영) → Crossword + Workbook
         → Translator → ImageFinder → Worksheet(시트 저장) → Reviewer(검수)
         → [발행하기] → 시트 상태 갱신 → 발행 사이트 노출
```

## Google Sheets 컬럼 (16개)

생성일시 | 레벨 | 섹션 | 토픽 | 단어수 | 기사(영문) | 기사(한국어) | 요약(한국어) |
어휘 | 출처 | 표절검사 | 이미지URL | 크로스워드 | 워크북Set1 | 워크북Set2 | **상태**

상태: 작성완료 → 발행완료 (타임스탬프). 헤더 변경 시 제자리 갱신(_ensure_header).

## Railway 환경변수

- ANTHROPIC_API_KEY (필수 — 생성 + 웹검색 + AI수정 전부 이것 하나)
- GOOGLE_SHEETS_CREDENTIALS_JSON (서비스 계정 JSON **내용 전체** — 파일 경로 아님!)
- GOOGLE_SHEET_ID = 1jA2lU16ImpYq1JxVl3hRLLLZn8cDGL6EKfnsQREsYQE
- UNSPLASH_ACCESS_KEY (미설정 시 코드 기본값)
- ~~GOOGLE_CSE_API_KEY / GOOGLE_CSE_ID~~ (폐기 — CSE 신규 고객 차단)

## 비용 (실측)

- 기사 1건 전체: 약 $0.17~0.24 (240원 내외, 표절 재작성 포함 시)
- 웹 검색: $10/1,000회 (max_uses=2)
- AI 수정/질문 1회: 약 $0.02
- 파이프라인 로그 마지막 줄 `Cost :`에 실측 출력
- 과금: console.anthropic.com 크레딧 (잔액 조회 API 없음)

## 발행 사이트 (ne-times-site)

- JP_Times(news-maker) 디자인 계승: 빨강/네이비, Noto Serif, 레벨 탭, 그리드
- 데이터: Railway `/api/published` fetch (CORS 허용됨)
- 기사 모달: 이미지 + 영어 본문 + 한국어 번역 토글 + 어휘
- index.html 상단 API_BASE 상수로 서버 주소 변경

## 알려진 한계 / v4 후보

- [ ] 멀티유저 동시 사용 시 usage_tracker 전역 카운터 섞임 (단일 사용자 가정)
- [ ] 히스토리 시트 복원 시 editing/review 필드는 빈 값 (시트에 미저장)
- [ ] 검수 거부돼도 시트엔 이미 저장됨 (순서: 저장 → 검수)
- [ ] 검수 거부 시 자동 재작성 루프 없음
- [ ] 배치 생성(여러 기사 동시) 미지원
- [ ] 누적 사용액/예상 잔액 표시 미구현 (시트에 비용 컬럼 추가 방식 논의됨)

---
마지막 수정: 2026-06-12 (v3 동결 — v4는 news-pipeline4에서 진행)
