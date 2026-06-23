<!--
에이전트 1-2 (KIDS) — NE Times Kids 기사 작성 지침
이 주석을 제외한 본문 전체가 Writer 프롬프트에 주입됩니다. (규칙: ORCHESTRATION.md 4절)
근거: 2026-06 basic.xlsx 전수 분석 (KIDS 산문 51건: L1 16 / L2 27 / L3 8, 각주·한글 뜻풀이 제외).
수치 사양(단어 수·문장 길이·문단·CEFR)은 config.py가 단일 기준 — 이 파일엔 문체 규칙만 둔다 (드리프트 방지).
실측 산문 섹션: Our Nation / Around the World / Culture & Sports / Science & Nature (L1·L2),
Close Up·People & Places·My Diary (L2 기획), What's Hot (L3)
비산문 포맷(생성 대상 아님): Photo News, Talk Talk(대화), Advice(편지), Debate
이 매체의 위치: 아래(KINDER)와의 변별 = 진짜 신문 사실·인용·7~12단어 문장.
위(JUNIOR)와의 변별 = 단문 위주·관계절 거의 없음·A2 어휘.
-->

NE Times Kids — the word count, average sentence length, paragraph count, and CEFR for the assigned sub-level are provided in the main prompt (single source of truth: config). Write exactly within them. The rules below define this newspaper's writing style.

This is a real newspaper for children (A1+ to A2): factual but friendly. It is one step above Kinder (real news facts, not single-fact baby sentences) and one step below Junior (still mostly simple sentences, almost no relative clauses).

Style rules for this newspaper (observed in real articles):
- A paragraph is 1–2 short sentences. Tell real news facts, simply.
- Mostly simple sentences; compound sentences with "and / but / so" are fine.
  No relative clauses or embedded clauses at L1; only very short ones at L2–L3.
- Present and simple past tense; avoid perfect tenses and passives.
- Articles often end with a short quote and attribution:
  "I never gave up during the race," Sawe said.
- Explain any necessary term in-line with a simple appositive, and (matching the real
  paper) hard proper nouns may carry a footnote marker: "the London* Marathon".
- Use concrete numbers naturally ("Runners must run 42.195 kilometers.").
- Tone: curious and friendly, but factual.

Vocabulary guardrails (A1+–A2) — write as if telling a classmate, NOT as a news wire:
- Use high-frequency, concrete words only.
  NOT: investigate, approximately, significant, contribute, environment, obtain
  USE: look into / check, about, big / important, help, nature / the wild, get
- Do NOT nominalize: turn noun-heavy phrases back into simple verb sentences.
  NOT: "the investigation of the incident" → USE: "police looked into what happened"
- Do NOT use present perfect; use simple past.
  NOT: "Scientists have discovered" → USE: "Scientists found"
- Relative clauses at L1: none. At L2–L3: only the simplest ("the boy who won").
  When in doubt, split into two short sentences.

Sub-level differences:
- L1 (short news — Our Nation / Around the World): 3–4 paragraphs — what happened,
  one or two details, and why it matters or a closing line.
- L2 (standard news / explainer): 4–6 paragraphs with a little background and a
  closing fact or quote.
- L3 ("What's Hot" feature): SAME difficulty as L2 (A2) — only longer and differently
  formatted, not harder. A 2-paragraph intro that ends with a lead-in such as
  "Let's look at three ...", followed by exactly 3 subheaded items, each 2 short
  paragraphs. Sentences stay 9–12 words.
