"""실제 NE Times 기사 CSV 4종을 분석해 매체×레벨별 범위 통계를 출력한다.

사용: python tests/analyze_media_csv.py <kinder.csv> <kids.csv> <junior.csv> <times.csv>
각주 줄(*로 시작)은 본문에서 제외. 뉴스 산문이 아닌 포맷(Photo News, 문답·대화·토론 등)은
수치 범위 계산에서 빼고 섹션 포맷으로만 집계한다.
"""

import csv
import re
import sys
from collections import defaultdict

# 산문 기사가 아닌 섹션 (수치 범위에서 제외, 포맷으로만 보고)
NON_PROSE = {
    "Photo News", "Did You Know", "Debate", "Debating",
    "Speak Out", "Talk Talk", "Think About It", "Advice",
}


def clean_body(body: str) -> list[str]:
    """각주(*) 줄을 제거하고 단락 리스트를 반환."""
    paragraphs = []
    for block in re.split(r"\n\s*\n", body):
        lines = [
            ln.strip() for ln in block.splitlines()
            if ln.strip() and not ln.strip().startswith("*")
        ]
        if lines:
            paragraphs.append(" ".join(lines))
    return paragraphs


def sentence_lengths(text: str) -> list[int]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [len(s.split()) for s in sentences if len(s.split()) >= 2]


def analyze(path: str, media: str):
    stats = defaultdict(list)   # level -> [(words, avg_sent_len, n_paragraphs)]
    sections = defaultdict(set)  # level -> {section}
    formats = defaultdict(set)   # level -> {non-prose section}

    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            level = row["레벨"].replace("LEVEL ", "L")
            section = row["섹션"].strip()
            sections[level].add(section)
            if section in NON_PROSE:
                formats[level].add(section)
                continue
            paragraphs = clean_body(row["본문"])
            text = " ".join(paragraphs)
            words = len(text.split())
            slens = sentence_lengths(text)
            avg_sl = sum(slens) / len(slens) if slens else 0
            stats[level].append((words, avg_sl, len(paragraphs)))

    print(f"\n=== {media} ({path.split(chr(92))[-1]}) ===")
    for level in sorted(stats):
        rows = stats[level]
        ws = sorted(r[0] for r in rows)
        sl = sorted(r[1] for r in rows)
        ps = sorted(r[2] for r in rows)
        print(
            f"  {level}: 기사 {len(rows)}건 | "
            f"단어 {ws[0]}–{ws[-1]} | "
            f"문장길이(평균) {sl[0]:.1f}–{sl[-1]:.1f} | "
            f"단락 {ps[0]}–{ps[-1]}"
        )
        print(f"      산문 섹션: {sorted(sections[level] - formats[level])}")
        if formats[level]:
            print(f"      비산문 포맷: {sorted(formats[level])}")
        # 개별 기사 (확인용)
        for w, s, p in sorted(rows):
            print(f"        - {w}단어 / 문장 {s:.1f} / {p}단락")


if __name__ == "__main__":
    paths = sys.argv[1:5]
    for path, media in zip(paths, ["KINDER", "KIDS", "JUNIOR", "TIMES"]):
        analyze(path, media)
