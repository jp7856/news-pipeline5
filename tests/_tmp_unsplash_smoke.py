"""Unsplash 검색 1회 스모크 — 키 값 미출력, 상태·건수만."""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

from config import UNSPLASH_ACCESS_KEY
print("키 설정 여부:", bool(UNSPLASH_ACCESS_KEY), f"(길이 {len(UNSPLASH_ACCESS_KEY)})")

if UNSPLASH_ACCESS_KEY:
    import requests
    resp = requests.get(
        "https://api.unsplash.com/search/photos",
        params={"query": "coral reef ocean", "per_page": 3, "orientation": "landscape"},
        headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
        timeout=10,
    )
    print("HTTP:", resp.status_code)
    if resp.ok:
        results = resp.json().get("results", [])
        print(f"결과: {len(results)}건")
        for r in results:
            print(f"  - {r.get('user', {}).get('name', '?')} / {r.get('urls', {}).get('regular', '')[:60]}...")
    else:
        print("응답:", resp.text[:150])
