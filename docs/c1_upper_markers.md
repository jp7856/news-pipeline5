# C1+ 상한 마커 리스트 — 1차안

> **목적**: 이 마커는 차단(reject) 게이트가 아니라 **기록·경고(log/warn)용**이다.  
> 마커가 몇 개 이상일 때 경고를 발생시킬지(임계값)는 실제 생성 데이터를 모은 뒤 별도로 정한다.  
>  
> 소스: `agents/guidelines/agent1_4_times.md` lines 32–51 (TIMES 어휘·구조 기준).  
> 외부 어휘 리스트 미사용 — guidelines에 명시된 항목만 수록.

---

## 1. 단일 어휘 마커

**1차안 적용: 즉시 가능**

단어 또는 구(phrase) 단위로 본문 내 존재 여부를 체크한다.

### L1 (B1) 금지 어휘

| NOT (금지) | USE (guidelines 제시 대체어) |
|---|---|
| proponents | supporters |
| deterring | stopping |
| incorporating | using |
| measurable margins | by a clear amount |
| civil liberties advocates | privacy / rights groups |

*근거 — guidelines 원문:*
> "L1 (B1): vocabulary a motivated Korean 9th-grader can read.  
> NOT: proponents, deterring, incorporating, measurable margins, civil liberties advocates  
> USE: supporters, stopping, using, by a clear amount, privacy / rights groups"

---

### L2/L3 (B2) C1+ 어휘

| NOT (금지) | USE (guidelines 제시 대체어) | 비고 |
|---|---|---|
| contend (that) | say | "civil liberties advocates **contend** that ..." |
| struggle to keep pace | cannot keep up | "regulations **struggle to keep pace**" |
| proliferation | spread / increase | 명사화 패턴 대표 어휘 → §3 참조 |

*근거 — guidelines 원문:*
> "Academic nominalizations and C1+ phrasing are NOT.  
> NOT: 'civil liberties advocates contend that existing regulations struggle to keep pace'  
> USE: 'privacy groups say the rules cannot keep up'"

---

## 2. 구조 카운트 마커

**1차안 적용: 즉시 가능**

텍스트 내 수치를 세어 임계값을 초과하면 플래그.  
*(임계값 숫자는 이 문서에서 정하지 않음 — 데이터 수집 후 확정)*

| 마커 | 판정 기준 | guidelines 원문 근거 |
|---|---|---|
| 30단어 초과 문장 | 문장 길이 > 30단어인 문장이 존재 | "A 30-word sentence is always a sign to split." |
| 대시(—) 2회 이상 | 본문 내 em-dash `—` 개수 ≥ 2 | "Dash insertions (— like this —): maximum ONE per article. They add complexity fast." |

---

## 3. Nominalization 패턴

**1차안 적용: 보류**  
*(대표 어휘 `proliferation`은 §1 L2/L3 마커에 포함; 패턴 자동 검출은 2차안)*

### 패턴 설명

`the + [명사화 동작 명사(-tion/-ment/-ance/-ence)] + of ...` 형태.  
동사 행위를 추상 명사로 감싸는 학술·문어체 구조.

### guidelines 예시 (원문 인용)

> NOT: "**the proliferation of** surveillance infrastructure"  
> USE: "more and more surveillance cameras are being installed"

### 검출 보류 사유

`-tion/-ment of` 정규식만으로는 false positive가 많다.  
예: "the election of a new president", "the development of a vaccine" — 정상 B2 표현.  
2차안에서 high-confidence 명사화 어휘 목록(C1 전형 어휘)과 결합해 구현 예정.

---

## 4. 구문·문체 패턴

**1차안 적용: 보류**  
*(패턴 자동 검출은 2차안)*

### 4-1. 학술 기관 인용 구조

> NOT: "Studies **conducted by criminologists at several universities in the United Kingdom  
> and the United States** have found that..."  
> USE: "Studies from UK and US universities show that..."

패턴: `Studies conducted by [전문직명] at [복수 기관명] ... have found/shown that`  
— 자동 검출 가능하나 1차안에서는 §1 "contend" 마커로 일부 커버.

### 4-2. 격식체 동사구

| 격식체 (C1+) | 평이체 대체 (guidelines) |
|---|---|
| contend that | say (→ §1에 단어 단위로 포함) |
| struggle to keep pace | cannot keep up (→ §1에 구 단위로 포함) |

*구 단위 전체 패턴 검출은 2차안 처리.*

### 4-3. 중첩 분사구·내포절 쌓기

> guidelines 원문: "No stacked participial phrases. No embedded clause inside another clause."

예시 구조: `[분사구, [관계절 [that절]]]` 형태의 3단 내포.  
— 자동 검출 로직의 복잡도가 높아 2차안으로 보류.

---

## 요약

| 분류 | 내용 | 1차안 적용 |
|---|---|---|
| 1. 단일 어휘 마커 | L1 금지 5개, L2/L3 C1+ 3개 | **즉시 가능** |
| 2. 구조 카운트 | 30단어 초과 문장, 대시 2회 이상 | **즉시 가능** |
| 3. Nominalization 패턴 | the [명사화] of … / 대표 어휘 §1 포함 | **보류** (2차안) |
| 4. 구문·문체 패턴 | 학술 인용 구조, 격식 동사구, 중첩절 | **보류** (2차안) |
