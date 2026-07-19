# -*- coding: utf-8 -*-
"""
jobkorea_bot.py
잡코리아(JobKorea) 통합검색 수집 봇

기능 요약
  - 8개 키워드를 순서대로 하나씩 검색하고, 뒤 페이지까지 전부 수집.
  - 지정한 검색조건 필터(기업형태/고용형태/경력/학력/등록일 1개월)를 전 키워드에 적용.
  - 검색결과 목록에서만 수집(상세페이지 미방문 → 빠름).
  - 공고 링크(job_id)가 같으면 동일 공고로 보고, '처음 걸린 키워드 / 처음 데이터'만 1줄로 기록.
  - 등록일은 실제 게재일 대신 '수집한 날짜'로 기록.
  - 재실행 시 기존 파일에 신규 공고만 누적 + 수집 60일 지난 공고는 자동 삭제.

필요 라이브러리:
    pip install requests beautifulsoup4 lxml

주의:
  * 개인/연구 목적의 소량 수집을 전제로 하며 요청 사이 지연을 둡니다.
  * 잡코리아 이용약관 및 robots 정책을 확인하고 과도한 트래픽을 유발하지 마세요.
  * 사이트 구조(HTML)는 수시로 바뀝니다. 파싱이 비면 parse_page()의 추출부를 조정하세요.
"""

import os
import csv
import re
import time
import random
from datetime import datetime, date, timedelta
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

# ===========================================================================
# 1) 설정 -- 여기만 바꾸면 됩니다
# ===========================================================================

# 검색 키워드 (이 순서가 중복 공고의 '첫 키워드' 우선순위가 됩니다)
KEYWORDS = ["마케팅", "해외영업", "신입", "공채", "글로벌", "marketing", "MD", "브랜드"]

# 검색조건 필터 (stext, Page_No 제외한 나머지 전부)
#  careerType=1,2      -> 신입 + 경력무관
#  careerMin/Max=1/3   -> 경력 1~3년
#  cotype=...          -> 기업형태 7종(대기업/중견/30대그룹사/외국계/외국기관/공공기관/매출1000대)
#  jobtype=1,3         -> 정규직 + 인턴
#  edu=5               -> 대학교졸업(4년제)
#  period=5            -> 등록일 최근 1개월
EXTRA_PARAMS = (
    "careerType=1,2&careerMin=1&careerMax=3"
    "&cotype=1,3,5,8,10,12,2,4,6,11"
    "&jobtype=1,3&tabType=recruit&edu=5&position=1&period=5"
)

# 지역 필터: 근무지역이 이 중 하나로 시작하는 공고만 저장 (빈 리스트 []면 전국)
#  ※ 잡코리아는 지역을 URL 파라미터로 안 담아서, 수집한 '근무지역' 값으로 코드에서 거른다.
LOCATION_FILTER = ["서울", "경기", "인천", "세종"]

# 수집 결과 파일 (재실행 시 신규 공고만 여기에 누적)
#  ※ 이 파일을 jobkorea_bot_main.py(타겟 매칭)의 입력으로 사용 → 파일명 jobkorea_list.csv 로 통일
MAIN_CSV = "jobkorea_list.csv"

# 안전장치: 키워드당 최대 페이지 수 (0 = 무제한, 신규 공고 없을 때까지)
MAX_PAGES = 0

# 수집일(수집일시) 기준 이 일수를 넘은 공고는 저장 시 자동 삭제
RETENTION_DAYS = 60

# 요청 사이 지연(초). 차단/서버부담 방지를 위해 반드시 유지하세요.
DELAY_RANGE = (1.2, 2.5)

BASE = "https://www.jobkorea.co.kr"
SEARCH_URL = BASE + "/Search/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Referer": BASE + "/",
}

# CSV 컬럼 순서
FIELDS = [
    "job_id", "키워드", "수집일시", "등록일",
    "기업명", "공고제목", "직무카테고리", "근무지역",
    "경력", "학력", "마감일", "공고링크",
]

# 파싱용 정규식
JOB_LINK_RE = re.compile(r"/Recruit/GI_Read/(\d+)")
REGION_RE = re.compile(
    r"^(서울|경기|인천|부산|대구|대전|광주|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주|전국|해외)"
)
CAREER_RE = re.compile(r"(경력무관|신입[\s·]*경력|신입|경력\s*\d+년?[↑~\d년\s]*|AD경력[\s\d년↑]*|경력)")
EDU_RE = re.compile(r"(학력무관|고졸|초대졸|대졸|대학교졸업|석사|박사|대졸\(4년\))")
DEADLINE_RE = re.compile(r"(D-\d+|오늘마감|내일마감|상시\s*채용|채용시|~\s*\d{1,2}/\d{1,2}|\d{1,2}/\d{1,2}\s*마감)")


# ===========================================================================
# 2) HTTP 요청 (재시도 포함)
# ===========================================================================
def fetch(session, url, retries=3):
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                return resp.text
            print(f"    [!] HTTP {resp.status_code} (시도 {attempt}/{retries})")
        except requests.RequestException as e:
            print(f"    [!] 요청 오류 (시도 {attempt}/{retries}): {e}")
        time.sleep(2 * attempt)
    return None


# ===========================================================================
# 3) 검색결과 한 페이지 파싱
#    핵심: /Recruit/GI_Read/{id} 링크는 사이트 개편에도 잘 유지되는 안정적 기준점.
#    이 링크가 든 카드(부모 요소) 단위로 묶어 필드를 뽑는다.
# ===========================================================================
def parse_page(html, keyword, today, now):
    soup = BeautifulSoup(html, "lxml")
    anchors = soup.find_all("a", href=JOB_LINK_RE)
    if not anchors:
        return [], False

    cards, order = {}, []
    for a in anchors:
        m = JOB_LINK_RE.search(a.get("href", ""))
        if not m:
            continue
        job_id = m.group(1)
        if job_id not in cards:
            card = a.find_parent(["li", "article"]) or a.find_parent("div") or a
            cards[job_id] = card
            order.append(job_id)

    jobs = []
    for job_id in order:
        card = cards[job_id]

        # 카드 내 공고 링크들의 텍스트 -> 제목/회사명 추정
        links = card.find_all("a", href=JOB_LINK_RE) if hasattr(card, "find_all") else []
        texts = [ln.get_text(strip=True) for ln in links if ln.get_text(strip=True)]
        texts = [t for t in texts if t not in ("스크랩", "로고")]
        title, company = "", ""
        if texts:
            title = max(texts, key=len)                         # 가장 긴 텍스트 = 제목
            others = [t for t in texts if t != title]
            company = min(others, key=len) if others else ""    # 나머지 짧은 것 = 회사명

        # 카드 전체 텍스트를 줄 단위로
        card_text = card.get_text("\n", strip=True) if hasattr(card, "get_text") else ""
        lines = [l.strip() for l in card_text.split("\n") if l.strip()]

        # 근무지역: 지역명으로 시작하는 라인
        location = next((l for l in lines if REGION_RE.match(l)), "")

        # 직무카테고리: 지역 라인 바로 다음의, 쉼표/가운뎃점이 든 라인
        job_category = ""
        if location and location in lines:
            idx = lines.index(location)
            for l in lines[idx + 1:]:
                if ("," in l or "·" in l) and "지원" not in l:
                    job_category = l
                    break

        # 경력 / 학력 / 마감일: 카드 텍스트에서 정규식으로 (없으면 공란)
        career = (CAREER_RE.search(card_text) or [""])[0] if CAREER_RE.search(card_text) else ""
        edu = (EDU_RE.search(card_text) or [""])[0] if EDU_RE.search(card_text) else ""
        deadline = (DEADLINE_RE.search(card_text) or [""])[0] if DEADLINE_RE.search(card_text) else ""

        jobs.append({
            "job_id": job_id,
            "키워드": keyword,
            "수집일시": now,
            "등록일": today,               # 실제 게재일 대신 수집한 날짜
            "기업명": company,
            "공고제목": title,
            "직무카테고리": job_category,
            "근무지역": location,
            "경력": career,
            "학력": edu,
            "마감일": deadline,
            "공고링크": f"{BASE}/Recruit/GI_Read/{job_id}",
        })

    return jobs, True


# ===========================================================================
# 4) 키워드 하나에 대해 전체 페이지 수집
# ===========================================================================
def scrape_keyword(session, keyword, seen_ids, today, now):
    print(f"\n=== '{keyword}' 수집 시작 ===")
    collected, page = [], 1
    while True:
        params = f"stext={quote(keyword)}&Page_No={page}"
        if EXTRA_PARAMS:
            params += "&" + EXTRA_PARAMS.lstrip("?&")
        url = f"{SEARCH_URL}?{params}"

        html = fetch(session, url)
        if html is None:
            print(f"  [x] {page}페이지 실패 → 중단")
            break

        jobs, has_results = parse_page(html, keyword, today, now)
        if not has_results or not jobs:
            print(f"  - {page}페이지: 결과 없음 → 종료")
            break

        new_count = 0
        for j in jobs:
            if j["job_id"] not in seen_ids:      # 전역 중복 제거(첫 키워드/첫 데이터 우선)
                seen_ids.add(j["job_id"])
                collected.append(j)
                new_count += 1

        print(f"  - {page}페이지: {len(jobs)}건 파싱 / 신규 {new_count}건 (키워드 누적 {len(collected)})")

        if new_count == 0:                       # 신규 없음 = 마지막 페이지 반복 → 종료
            print("  - 신규 공고 없음 → 종료")
            break

        page += 1
        if MAX_PAGES and page > MAX_PAGES:
            print(f"  - MAX_PAGES({MAX_PAGES}) 도달 → 종료")
            break
        time.sleep(random.uniform(*DELAY_RANGE))

    print(f"=== '{keyword}' 완료: {len(collected)}건 ===")
    return collected


# ===========================================================================
# 5) 메인 파일 로드/저장 (재실행 시 신규만 누적)
# ===========================================================================
def load_existing(path):
    """기존 메인 CSV -> (기존 행 리스트, 이미 있는 job_id 집합)"""
    rows, ids = [], set()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                rows.append(row)
                if row.get("job_id"):
                    ids.add(row["job_id"])
        print(f"[로드] 기존 메인 파일 {len(rows)}건 (등록일 보존)")
    else:
        print("[로드] 기존 메인 파일 없음 → 새로 생성")
    return rows, ids


def region_ok(row):
    """근무지역이 LOCATION_FILTER 중 하나로 시작하면 True (필터 비었으면 전부 통과)."""
    if not LOCATION_FILTER:
        return True
    loc = row.get("근무지역", "") or ""
    return any(loc.startswith(r) for r in LOCATION_FILTER)


def save_main(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in FIELDS})
    print(f"[저장] {path} (총 {len(rows)}건)")


def prune_old(rows, days):
    """수집일시가 days일 넘은 행 제거. 파싱 실패 시 안전하게 유지."""
    cutoff = date.today() - timedelta(days=days)
    keep, removed = [], 0
    for r in rows:
        ts = (r.get("수집일시") or "").strip()
        try:
            d = datetime.strptime(ts[:10], "%Y-%m-%d").date()
        except ValueError:
            d = None
        if d is None or d >= cutoff:
            keep.append(r)
        else:
            removed += 1
    return keep, removed


# ===========================================================================
# 6) 메인
# ===========================================================================
def main():
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    session = requests.Session()
    existing_rows, seen_ids = load_existing(MAIN_CSV)  # 기존 job_id는 seen에 포함 → 재수집 안 함

    new_rows = []
    for kw in KEYWORDS:
        new_rows.extend(scrape_keyword(session, kw, seen_ids, today, now))
        time.sleep(random.uniform(*DELAY_RANGE))

    # 지역 필터 적용 (서울/경기/인천/세종만 남김)
    before = len(new_rows)
    new_rows = [r for r in new_rows if region_ok(r)]
    print(f"[지역필터] {before}건 → {len(new_rows)}건 (기준: {LOCATION_FILTER or '전국'})")

    all_rows = existing_rows + new_rows            # 기존 + 신규 누적
    all_rows, removed = prune_old(all_rows, RETENTION_DAYS)   # 수집 60일 초과 자동 삭제
    print(f"\n########## 신규 {len(new_rows)}건 / 삭제 {removed}건 / 전체 {len(all_rows)}건 ##########")
    save_main(MAIN_CSV, all_rows)


if __name__ == "__main__":
    main()