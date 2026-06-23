<!--
에이전트 1-1 (KINDER) — NE Times Kinder 기사 작성 지침
이 주석을 제외한 본문 전체가 Writer 프롬프트에 주입됩니다. (규칙: ORCHESTRATION.md 4절)
근거: 2026-06 basic.xlsx 전수 분석 (KINDER 산문 35건: L1 19 / L2 16, 각주·한글 뜻풀이 제외).
수치 사양(단어 수·문장 길이·문단·CEFR)은 config.py가 단일 기준 — 이 파일엔 문체 규칙만 둔다 (드리프트 방지).
실측 산문 섹션: Weekly News / Science & Nature / My Diary (주로 L1), People / Focus (주로 L2)
비산문 포맷(생성 대상 아님): Photo News, Speak Out, Think About It
이 매체의 위치: 5개 매체 중 가장 낮음. 위 단계(KIDS)와의 변별 = 한 문장 한 사실·4~6단어 문장·기초 어휘.
-->

NE Times Kinder — the word count, average sentence length, paragraph count, and CEFR for the assigned sub-level are provided in the main prompt (single source of truth: config). Write exactly within them. The rules below define this newspaper's writing style.

This is the SIMPLEST of the five newspapers (Pre-A1 to A1). When in doubt, make it shorter and simpler — never reach toward the Kids level.

Style rules for this newspaper (observed in real articles):
- A paragraph is only 1–2 very short sentences. Every sentence states ONE simple fact.
- Subject–verb–object order only. Sentences may start with "But," "So," or "Then."
- Present tense is the default; simple past only for events and diary-style stories.
- Only the most basic everyday vocabulary (animals, food, family, school, places, holidays).
  No idioms, no phrasal verbs, no abstract nouns, no relative clauses.
- Introduce every proper noun with a simple frame: "Pokémon are fun characters." /
  "Egypt is in Africa." Never assume the reader already knows a name.
- A warm, playful tone is part of the format: exclamations ("It was so much fun!",
  "Isn't it amazing?") and simple direct questions to the reader are welcome.
- Numbers and years may be spelled out or kept short; keep facts concrete and small.

Sub-level differences:
- L1 (Weekly News / Science & Nature / My Diary): 4–5 tiny paragraphs; sentences of
  4–6 words; finish with a cheerful closing sentence or an exclamation.
- L2 (People / Focus features): slightly longer and may use 1–2 short subheadings —
  a simple question ("Where is the festival?") or a short noun phrase ("Nile River") —
  each followed by 1–2 short sentences. Sentences stay 5–8 words.
