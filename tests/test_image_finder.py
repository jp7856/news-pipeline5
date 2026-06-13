"""ImageFinder 변별력 검증 — 기존 이미지 제외·후보 중 선택."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from types import SimpleNamespace as NS

from agents.image_finder import ImageFinderAgent

BASE = "https://images.unsplash.com/photo-{n}"


def make_agent(candidates_by_query):
    agent = ImageFinderAgent.__new__(ImageFinderAgent)
    agent._log = lambda m: None
    agent._search_images = lambda q: candidates_by_query.get(q, [])
    return agent


def make_pkg():
    return NS(
        article=NS(vocabulary=["election", "vote"]),
        topic="선거",
        section=NS(name="POLITICS"),
        image_url="",
    )


# 1) URL 정규화 — 쿼리스트링이 달라도 같은 사진으로 식별
a = BASE.format(n=1) + "?w=1080&q=80"
b = BASE.format(n=1) + "?w=400"
assert ImageFinderAgent._normalize(a) == ImageFinderAgent._normalize(b)
print("normalize OK")

# 2) 제외 목록에 있는 이미지는 선택하지 않음
cands = [BASE.format(n=i) + "?w=1080" for i in range(1, 6)]
agent = make_agent({"election vote": cands})
pkg = make_pkg()
used = [BASE.format(n=1) + "?w=400", BASE.format(n=2) + "?q=80"]  # 1,2번 사용됨
for _ in range(20):  # 무작위 선택이므로 반복 확인
    pkg.image_url = ""
    agent.run(pkg, exclude_urls=used)
    assert pkg.image_url, "이미지를 못 찾음"
    assert ImageFinderAgent._normalize(pkg.image_url) not in {
        ImageFinderAgent._normalize(u) for u in used
    }, f"제외된 이미지가 선택됨: {pkg.image_url}"
print("exclusion OK")

# 3) 첫 검색어 후보가 전부 중복이면 다음 검색어로 폴백
agent = make_agent({
    "election vote": [BASE.format(n=1)],
    "election": [BASE.format(n=9)],
})
pkg = make_pkg()
agent.run(pkg, exclude_urls=[BASE.format(n=1)])
assert pkg.image_url.startswith(BASE.format(n=9)), pkg.image_url
print("fallback OK")

# 4) 제외 목록이 없으면 상위 후보 중에서 선택 (단일 고정 아님 — 풀 검증)
agent = make_agent({"election vote": cands})
picked = set()
for _ in range(60):
    pkg = make_pkg()
    agent.run(pkg)
    picked.add(ImageFinderAgent._normalize(pkg.image_url))
assert len(picked) > 1, "항상 같은 이미지만 선택됨"
print("diversity OK")

print("ALL TESTS PASSED")
