"""TIMES L1 기사 생성 테스트 — CEFR 게이트 통과율 확인. API 호출 있음.

실행: cd news-pipeline5 && python -m tests.test_times_l1_gen
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from models import Level, Section
from agents.level_agents import Agent1_4Times
from agents.sub_agents.cefr_checker import validate, LEVELS

TOPICS = [
    ("South Korea's record heat wave this summer",     Section.ENVIRONMENT),
    ("BTS member Jin returns from military service",   Section.CULTURE),
    ("South Korea raises minimum wage for 2026",       Section.ECONOMY),
    ("New AI tools changing how students study",       Section.EDUCATION),
]

spec = LEVELS["TIMES_L1"]
print(f"TIMES_L1 임계값 — avg_min={spec.avg_min}, fk_max={spec.fk_max}")
print("=" * 72)

for idx, (topic, section) in enumerate(TOPICS, 1):
    logs: list[str] = []

    def log_cb(msg: str, _logs=logs):
        _logs.append(msg)
        print(f"  LOG: {msg}")

    agent = Agent1_4Times(log_callback=log_cb)

    print(f"\n[{idx}] 토픽: {topic}")
    print(f"     섹션: {section.value}")

    try:
        article, plag = agent.produce_article(topic, Level.TIMES, section, sub_level="L1")
    except Exception as e:
        print(f"  !! 생성 오류: {e}")
        continue

    # 재작성 횟수: 로그에서 "재작성 N/3회" 패턴 카운트
    rewrites = sum(1 for l in logs if "재작성" in l and "/3회" in l and "CEFR" in l)
    total_rewrites = sum(1 for l in logs if "재작성" in l and "/3회" in l)

    # 최종 기사 CEFR 측정
    r = validate(article.text, "TIMES_L1")

    status = "✓ 통과" if r.passed else "✗ 실패"
    easy   = " [too_easy]" if r.too_easy else ""
    fk_over = any("FK" in v and "참고" not in v for v in r.violations)

    print(f"\n  결과: {status}{easy}")
    print(f"  avg_sentence_len = {r.avg_sentence_len:.1f}  (하한 {spec.avg_min})")
    print(f"  FK = {r.fk_grade}  (상한 {spec.fk_max})")
    print(f"  word_count = {article.word_count}")
    print(f"  총 재작성 횟수 = {total_rewrites}회 (CEFR 원인 = {rewrites}회)")
    if r.violations:
        for v in r.violations:
            hint = " [소프트]" if "참고" in v else " [하드게이트]"
            print(f"  위반: {v}{hint}")
    print(f"  표절 = {'통과' if plag.passed else '경고'}")
    print("-" * 72)
