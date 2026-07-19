# -*- coding: utf-8 -*-
"""
select_new.py
세 사이트의 매칭 결과(*_main.csv)에서 '오늘 새로 수집됐고, 아직 알림 안 보낸' 공고만 추린다.

동작
  - jobkorea_main.csv / saramin_main.csv / peoplenjob_main.csv 를 읽음
  - 수집일시 날짜가 '오늘'인 행만 남김
  - notified_jobs.csv 에 이미 기록된(=이미 텔레그램으로 보낸) 공고는 제외
  - 세 사이트 결과를 하나로 합쳐 리스트로 반환 (출처/공고ID/notify_key 부여)

이 파일은 '추리기'만 한다. AI 판정·전송·기록은 다른 파일(ai_filter / telegram_send / run_daily)이 담당.
notified 기록 헬퍼(load/append)도 여기 모아둬서 run_daily 가 전송 후 호출한다.
"""

import os
import csv
from datetime import date

# ===========================================================================
# 설정
# ===========================================================================
# (출처이름, 파일명, 그 파일의 고유번호 컬럼)
SOURCES = [
    ("jobkorea",   "jobkorea_main.csv",   "job_id"),
    ("saramin",    "saramin_main.csv",    "rec_idx"),
    ("peoplenjob", "peoplenjob_main.csv", "job_id"),
]

NOTIFIED_CSV = "notified_jobs.csv"        # 이미 보낸 공고 기록(중복 알림 방지)
NOTIFIED_FIELDS = ["notify_key", "출처", "공고ID", "기업명", "공고제목", "알림일시"]

DATE_COL = "수집일시"                      # 이 컬럼의 날짜로 '오늘' 판정


# ===========================================================================
# notified 기록 로드/추가
# ===========================================================================
def load_notified(path=NOTIFIED_CSV):
    """이미 알림 보낸 notify_key 집합 반환."""
    keys = set()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                k = (row.get("notify_key") or "").strip()
                if k:
                    keys.add(k)
    return keys


def append_notified(rows, path=NOTIFIED_CSV, now_str=""):
    """전송 완료한 공고들을 notified 기록에 추가(누적)."""
    exists = os.path.exists(path)
    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=NOTIFIED_FIELDS)
        if not exists:
            writer.writeheader()
        for r in rows:
            writer.writerow({
                "notify_key": r.get("notify_key", ""),
                "출처": r.get("출처", ""),
                "공고ID": r.get("공고ID", ""),
                "기업명": r.get("기업명", ""),
                "공고제목": r.get("공고제목", ""),
                "알림일시": now_str,
            })


# ===========================================================================
# 오늘 신규 추리기
# ===========================================================================
def _read_source(source, path, id_col, today_str, notified):
    if not os.path.exists(path):
        print(f"[스킵] {path} 없음")
        return []
    out = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            # 오늘 수집분만
            if (row.get(DATE_COL, "") or "")[:10] != today_str:
                continue
            job_id = (row.get(id_col) or "").strip()
            if not job_id:
                continue
            key = f"{source}:{job_id}"
            if key in notified:                 # 이미 보낸 공고 제외
                continue
            row = dict(row)
            row["출처"] = source
            row["공고ID"] = job_id
            row["notify_key"] = key
            out.append(row)
    print(f"[{source}] 오늘 신규 {len(out)}건")
    return out


def get_today_new(notified_path=NOTIFIED_CSV, today_str=None):
    """세 사이트에서 오늘 신규·미알림 공고를 모아 리스트로 반환."""
    today_str = today_str or date.today().isoformat()
    notified = load_notified(notified_path)
    merged = []
    for source, path, id_col in SOURCES:
        merged.extend(_read_source(source, path, id_col, today_str, notified))
    print(f"[합계] 오늘 신규·미알림 총 {len(merged)}건 (기준일 {today_str})")
    return merged


# ===========================================================================
# 단독 실행: 오늘 신규 목록 미리보기
# ===========================================================================
if __name__ == "__main__":
    rows = get_today_new()
    for r in rows[:20]:
        print(f"  - [{r['출처']}] {r.get('기업명','')} | {str(r.get('공고제목',''))[:34]} | {r.get('공고링크','')}")
    if not rows:
        print("  (오늘 새로 올라온 공고 없음)")
