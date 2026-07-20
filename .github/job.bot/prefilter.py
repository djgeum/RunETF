# -*- coding: utf-8 -*-
"""
prefilter.py
공고 제목만 보고 '관련 없는 직무'를 규칙(단어)으로 미리 걸러낸다. (Gemini 호출 전 대량 축소)

- 단어 목록은 filter_words.txt 에서 읽는다(코드 수정 없이 그 파일만 편집하면 됨).
- 판정: 제목에 DROP 단어 있으면 제외 → 아니면 KEEP 단어 있으면 통과 → 둘 다 없으면 제외.
- run_daily 가 select_new 결과를 여기로 먼저 통과시킨 뒤, 살아남은 소수만 ai_filter 로 넘긴다.

이 단계는 API 를 전혀 쓰지 않는다(무료·즉시).
"""

import os
import sys
import csv

WORDS_FILE = "filter_words.txt"
TITLE_COL = "공고제목"
CANDIDATES_CSV = "prefiltered.csv"        # 제목필터 통과 목록(=Gemini 판정 대상) 저장 파일


def load_filter_words(path=WORDS_FILE):
    """filter_words.txt -> (keep 리스트, drop 리스트). 소문자화."""
    keep, drop, section = [], [], None
    if not os.path.exists(path):
        print(f"[제목필터] 단어파일 없음: {path} (필터 미적용)")
        return keep, drop
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            low = s.lower()
            if low == "[keep]":
                section = "keep"; continue
            if low == "[drop]":
                section = "drop"; continue
            if section == "keep":
                keep.append(low)
            elif section == "drop":
                drop.append(low)
    return keep, drop


def title_pass(title, keep, drop):
    """제목이 통과하면 True."""
    t = (title or "").lower()
    if any(w in t for w in drop):      # DROP 우선
        return False
    if any(w in t for w in keep):
        return True
    return False


def filter_rows(rows, path=WORDS_FILE, title_col=TITLE_COL):
    """dict 리스트에서 제목이 통과하는 행만 반환."""
    keep, drop = load_filter_words(path)
    if not keep and not drop:
        return rows                    # 단어파일 없으면 그대로 통과
    out = [r for r in rows if title_pass(r.get(title_col, ""), keep, drop)]
    print(f"[제목필터] {len(rows)}건 → {len(out)}건 통과 "
          f"(KEEP {len(keep)}단어 / DROP {len(drop)}단어)")
    return out


def save_candidates(rows, path=CANDIDATES_CSV):
    """제목필터를 통과한 목록(=Gemini 판정 대상)을 CSV로 저장(검토용)."""
    # 사이트마다 컬럼이 조금 달라서, 등장하는 모든 키를 합쳐 헤더로 사용
    keys = []
    for r in rows:
        for k in r.keys():
            if k not in keys:
                keys.append(k)
    if not keys:
        keys = ["출처", "공고ID", "기업명", "공고제목", "공고링크"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print(f"[제목필터] 통과 목록 저장: {path} ({len(rows)}건)")
    return path


# ===========================================================================
# 단독 실행: CSV 하나에 필터를 적용해 통과/제외 미리보기
#   python prefilter.py jobkorea_main.csv
# ===========================================================================
if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "jobkorea_main.csv"
    if not os.path.exists(path):
        print(f"파일 없음: {path}")
        raise SystemExit(0)
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    keep, drop = load_filter_words()
    passed = [r for r in rows if title_pass(r.get(TITLE_COL, ""), keep, drop)]
    dropped = [r for r in rows if not title_pass(r.get(TITLE_COL, ""), keep, drop)]
    print(f"\n[{path}] 총 {len(rows)}건 → 통과 {len(passed)} / 제외 {len(dropped)}\n")
    print("--- 통과(앞 10) ---")
    for r in passed[:10]:
        print("  O", str(r.get(TITLE_COL, ""))[:50])
    print("--- 제외(앞 10) ---")
    for r in dropped[:10]:
        print("  X", str(r.get(TITLE_COL, ""))[:50])
