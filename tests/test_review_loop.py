import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from types import SimpleNamespace as NS
from models import ReviewResult, ArticleStatus
from agents.reviewer import ReviewerAgent
from agents.worksheet import WorksheetAgent

# 1) _status_label
pkg = NS(review_result=None)
assert WorksheetAgent._status_label(pkg) == '작성완료'
pkg.review_result = ReviewResult(passed=True, status=ArticleStatus.APPROVED)
assert WorksheetAgent._status_label(pkg) == '작성완료'
pkg.review_result = ReviewResult(passed=False, status=ArticleStatus.REJECTED, notes='x')
assert WorksheetAgent._status_label(pkg) == '검수거부'
pkg.review_result = ReviewResult(passed=False, status=ArticleStatus.ERROR, notes='boom')
assert WorksheetAgent._status_label(pkg) == '검수오류'
print('status_label OK')

# 2) reviewer JSON 파싱 (fix_targets 검증 포함)
r = ReviewerAgent.__new__(ReviewerAgent)
r._log = lambda m: None

class FakeMsgs:
    def __init__(self, text): self.text = text
    def create(self, **kw): return NS(content=[NS(text=self.text)], usage=None)

fake_pkg = NS(level=NS(value='junior'), section=NS(value='환경'), topic='t',
    article=NS(word_count=300, vocabulary=['a'], text_ko='ko', summary_ko='s', text='body'),
    image_url='', plagiarism_report=NS(passed=True), crossword_sentences=[], workbook_sets=[],
    review_result=None)

r._client = NS(messages=FakeMsgs(json.dumps(
    {'approved': False, 'reason': '번역 어색', 'fix_targets': ['translation', 'bogus']})))
ok, reason, targets = r._review(fake_pkg)
assert ok is False and targets == ['translation'], (ok, targets)

r._client = NS(messages=FakeMsgs(json.dumps({'approved': True, 'reason': 'good'})))
ok, reason, targets = r._review(fake_pkg)
assert ok is True and targets == []
print('reviewer parse OK')

# 3) run() 경유 시 ReviewResult.fix_targets 채워지는지
r._client = NS(messages=FakeMsgs(json.dumps(
    {'approved': False, 'reason': 'r', 'fix_targets': ['workbook']})))
out = r.run(fake_pkg)
assert out.review_result.fix_targets == ['workbook']
assert out.review_result.status == ArticleStatus.REJECTED
print('reviewer run OK')

# 4) 오케스트레이터 재작성 루프 — 스텁으로 전체 흐름 검증
from orchestrator import Orchestrator

logs = []
o = Orchestrator(log_callback=logs.append)

class StubReviser:
    def __init__(self, **kw): pass
    def run(self, article, instruction, level, plagiarism_report=None, history=None):
        return article, '수정했습니다', True

import agents.sub_agents.reviser as reviser_mod
reviser_mod.ReviserAgent = StubReviser

calls = {'plag': 0, 'translate': 0, 'crossword': 0, 'workbook': 0}
producer = NS(
    _plagcheck=NS(run=lambda a: (calls.__setitem__('plag', calls['plag'] + 1), NS(passed=True))[1]),
    _crossword=NS(run=lambda a: (calls.__setitem__('crossword', calls['crossword'] + 1), ['cw'])[1]),
    _workbook=NS(run=lambda a, l: (calls.__setitem__('workbook', calls['workbook'] + 1), ['wb'])[1]),
)
translator = NS(run=lambda p: (calls.__setitem__('translate', calls['translate'] + 1), p)[1])

pkg2 = NS(
    review_result=ReviewResult(passed=False, status=ArticleStatus.REJECTED,
                               notes='기사 수준이 레벨과 안 맞음', fix_targets=['article']),
    article=NS(text='body'), level=NS(value='junior'),
    plagiarism_report=NS(passed=True),
    crossword_sentences=[], workbook_sets=[],
)
out = o._fix_rejected(pkg2, producer, translator, 1, 2)
# article 수정 → 표절 재검사 1회 + 번역 자동 갱신 1회
assert calls == {'plag': 1, 'translate': 1, 'crossword': 0, 'workbook': 0}, calls

# fix_targets 비어 있으면 article 기본값
pkg2.review_result = ReviewResult(passed=False, status=ArticleStatus.REJECTED, notes='이유', fix_targets=[])
out = o._fix_rejected(pkg2, producer, translator, 2, 2)
assert calls['plag'] == 2 and calls['translate'] == 2

# crossword/workbook만 대상일 때 기사·번역은 건드리지 않음
pkg2.review_result = ReviewResult(passed=False, status=ArticleStatus.REJECTED, notes='워크북 없음',
                                  fix_targets=['crossword', 'workbook'])
out = o._fix_rejected(pkg2, producer, translator, 1, 2)
assert calls == {'plag': 2, 'translate': 2, 'crossword': 1, 'workbook': 1}, calls
assert out.crossword_sentences == ['cw'] and out.workbook_sets == ['wb']
print('fix_rejected dispatch OK')

# 5) FactChecker — JSON 파싱·출처 없음 생략·이슈 시 불통과
from agents.sub_agents.fact_checker import FactCheckerAgent

fc = FactCheckerAgent.__new__(FactCheckerAgent)
fc._log = lambda m: None
fake_article = NS(text='The tower is 184 meters tall.')
srcs = [{'title': 'Sky Bridge', 'snippet': 'observatory 184m', 'date': '2026-04'}]

# 출처 없으면 점검 생략하고 통과
ok, issues = fc.run(fake_article, [])
assert ok is True and issues == []

fc._client = NS(messages=FakeMsgs(json.dumps({'passed': True, 'issues': []})))
ok, issues = fc.run(fake_article, srcs)
assert ok is True and issues == []

fc._client = NS(messages=FakeMsgs(json.dumps(
    {'passed': False, 'issues': ['기사 수치 200m가 출처(184m)와 모순']})))
ok, issues = fc.run(fake_article, srcs)
assert ok is False and len(issues) == 1

# passed=true인데 issues가 있으면 불통과 처리
fc._client = NS(messages=FakeMsgs(json.dumps({'passed': True, 'issues': ['의심 항목']})))
ok, issues = fc.run(fake_article, srcs)
assert ok is False

# API 오류 시 통과 처리 (파이프라인 계속)
class BoomMsgs:
    def create(self, **kw): raise RuntimeError('boom')
fc._client = NS(messages=BoomMsgs())
ok, issues = fc.run(fake_article, srcs)
assert ok is True
print('fact checker OK')

print('ALL TESTS PASSED')
