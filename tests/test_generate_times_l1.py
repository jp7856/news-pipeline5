"""TIMES_L1 기사 테스트 생성 — CEFR 게이트 통과 여부 확인.

API 호출 있음 (Writer + PlagChecker + FactCheck per article).
각 기사: 초안 → 재작성 루프 → 최종 validate() 재측정.
"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

from models import Level, Section
from agents.level_agents import create_agent1
from agents.sub_agents.cefr_checker import validate, LEVELS

TOPICS = [
    ("South Korea's Push for AI Education Reform",     Section.EDUCATION),
    ("World Cup 2026: What Fans Can Expect",            Section.SPORTS),
    ("Plastic Pollution in the Korean Ocean",           Section.ENVIRONMENT),
    ("South Korea's Aging Population Challenge",        Section.SOCIETY),
]

spec = LEVELS["TIMES_L1"]
print(f"TIMES_L1 임계값: avg_min={spec.avg_min}  fk_max={spec.fk_max}")
print(f"{'='*70}")

for i, (topic, section) in enumerate(TOPICS, 1):
    logs: list[str] = []
    agent = create_agent1(Level.TIMES, log_callback=logs.append)

    print(f"\n[{i}/{len(TOPICS)}] {topic}")
    print(f"  섹션: {section.value}")

    try:
        article, plag = agent.produce_article(
            topic, Level.TIMES, section, sub_level="L1"
        )

        # 최종 기사 CEFR 재측정
        r = validate(article.text, "TIMES_L1")

        # 재작성 횟수: 로그에서 "재작성 N/3회" 중 최대 N 추출
        attempts = [int(m) for m in re.findall(r"재작성\s+(\d+)/3회", "\n".join(logs))]
        total_rewrites = max(attempts) if attempts else 0
        cefr_rewrites  = sum(1 for l in logs if "CEFR 난이도 위반" in l)

        status = "✓ PASS" if r.passed else ("✗ FAIL (too_easy)" if r.too_easy else "✗ FAIL (FK↑)")
        print(f"  → {status}")
        print(f"     avg={r.avg_sentence_len:.1f}단어  FK={r.fk_grade}  "
              f"문장수={r.sentence_count}  wc={article.word_count}")
        print(f"     재작성: 총 {total_rewrites}회 (CEFR 원인 {cefr_rewrites}회)")
        if r.violations:
            for v in r.violations:
                tag = "(하드)" if "참고" not in v else "(소프트)"
                print(f"     ⤷ {tag} {v}")

    except Exception as e:
        print(f"  오류: {e}")
        import traceback; traceback.print_exc()

print(f"\n{'='*70}")
print("완료.")
