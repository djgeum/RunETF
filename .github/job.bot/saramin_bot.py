# -*- coding: utf-8 -*-
"""
saramin_bot.py
사람인(Saramin) 통합검색 수집 봇  (구조는 jobkorea_bot.py 와 동일)

기능 요약
  - 8개 키워드를 순서대로 하나씩 검색하고, 뒤 페이지까지 전부 수집.
  - 검색조건 필터(기업형태 8종 / 지역 5곳)를 URL로 서버에서 적용.
  - 검색결과 목록에서만 수집(상세페이지 미방문 → 빠름).
  - 공고 고유번호(rec_idx)가 같으면 동일 공고로 보고, '처음 걸린 키워드 / 처음 데이터'만 1줄로 기록.
  - 사람인은 목록에 실제 등록일/수정일이 있어 그대로 저장. 등록일(없으면 수정일) 기준 최근 1개월만 남김.
  - 결과를 CSV(utf-8-sig) 메인 파일로 저장. 재실행 시 기존 파일에 신규 공고만 누적.

필요 라이브러리:
    pip install requests beautifulsoup4 lxml

주의:
  * 개인/연구 목적의 소량 수집을 전제로 하며 요청 사이 지연을 둡니다.
  * 사람인 이용약관 및 robots 정책을 확인하고 과도한 트래픽을 유발하지 마세요.
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

# 검색조건 필터 (searchword, recruitPage 제외한 나머지 전부)
#  loc_mcd      -> 지역: 인천(108000)·서울(101000)·세종(118000)·경기(102000)·대전(105000)
#  company_type -> 기업형태 8종(대기업/외국계/코스닥/중견/공사공기업/코스피/중소/외부감사법인)
#  company_cd   -> 추가 선택 코드(URL 값 그대로)
EXTRA_PARAMS = (
    "searchType=search"
    "&company_cd=0,1,2,3,4,5,6,7,9,10"
    "&loc_mcd=108000,101000,118000,102000,105000"
    "&company_type=scale001,foreign,kosdaq,scale002,public,kospi,scale003,incorporated"
    "&panel_type=&search_optional_item=y&search_done=y&panel_count=y&preview=y"
)

# 최근 N일 이내 등록(없으면 수정)된 공고만 저장  (1개월 = 31)
RECENT_DAYS = 31

# 메인 데이터 파일 (재실행 시 신규 공고만 여기에 누적)
MAIN_CSV = "saramin_list.csv"

# 안전장치: 키워드당 최대 페이지 수 (0 = 무제한, 신규 공고 없을 때까지)
MAX_PAGES = 0

# 수집일(수집일시) 기준 이 일수를 넘은 공고는 저장 시 자동 삭제
RETENTION_DAYS = 60

# 요청 사이 지연(초). 차단/서버부담 방지를 위해 반드시 유지하세요.
DELAY_RANGE = (1.2, 2.5)

BASE = "https://www.saramin.co.kr"
SEARCH_URL = BASE + "/zf_user/search"

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
    "rec_idx", "키워드", "수집일시", "등록일", "날짜구분",
    "기업명", "공고제목", "직무카테고리", "근무지역",
    "경력", "학력", "고용형태", "마감일", "공고링크",
]

# 파싱용 정규식
REC_IDX_RE = re.compile(r"rec_idx=(\d+)")
REGION_RE = re.compile(
    r"^(서울|경기|인천|부산|대구|대전|광주|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주|전국|해외)"
)
CAREER_RE = re.compile(r"(신입·경력|경력무관|신입|경력\s*\d+~?\d*년?[↑\s]*|경력)")
EDU_RE = re.compile(r"(학력무관|고졸|초대졸|대졸|대학원|석사|박사)[↑]?")
EMPTYPE_RE = re.compile(r"(정규직·인턴직|정규직|계약직|인턴직|인턴|아르바이트|파견직|프리랜서|파트|위촉직|병역특례|교육생)")
DATE_RE = re.compile(r"(등록일|수정일)\s*(\d{2})/(\d{2})/(\d{2})")
DEADLINE_RE = re.compile(r"(~\s*\d{1,2}/\d{1,2}\s*\([월화수목금토일]\)|오늘마감|내일마감|상시\s*채용|채용시|D-\d+)")


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
#    사람인 목록의 각 공고는 div.item_recruit 단위. 마크업이 바뀌면 rec_idx 링크
#    기준으로도 묶을 수 있게 폴백을 둔다.
# ===========================================================================
def _classify_conditions(spans_text):
    """조건 span 텍스트 목록에서 지역/경력/학력/고용형태를 분류."""
    location = career = edu = emptype = ""
    for t in spans_text:
        t = t.strip()
        if not t:
            continue
        if not location and REGION_RE.match(t):
            location = t
        elif not emptype and EMPTYPE_RE.fullmatch(t):
            emptype = t
        elif not edu and EDU_RE.fullmatch(t):
            edu = t
        elif not career and CAREER_RE.search(t):
            career = t
    return location, career, edu, emptype


def parse_page(html, keyword, now):
    soup = BeautifulSoup(html, "lxml")

    # 기본: div.item_recruit / 폴백: rec_idx 링크가 든 카드
    items = soup.select("div.item_recruit")
    if not items:
        anchors = soup.find_all("a", href=REC_IDX_RE)
        seen, items = set(), []
        for a in anchors:
            rid = REC_IDX_RE.search(a.get("href", "")).group(1)
            if rid in seen:
                continue
            seen.add(rid)
            card = a.find_parent(["div", "li"]) or a
            items.append(card)

    if not items:
        return [], False

    jobs = []
    for item in items:
        # rec_idx
        rid = ""
        a_link = item.find("a", href=REC_IDX_RE)
        if a_link:
            rid = REC_IDX_RE.search(a_link.get("href", "")).group(1)
        elif item.get("value", "").isdigit():
            rid = item.get("value")
        if not rid:
            continue

        # 제목
        tit = item.select_one(".job_tit a, .str_tit, h2.job_tit a")
        title = ""
        if tit:
            title = tit.get("title", "").strip() or tit.get_text(strip=True)

        # 기업명
        corp = item.select_one(".corp_name a, .corp_name, .company_nm a, .str_tit")
        company = corp.get_text(strip=True) if corp else ""

        # 조건(지역/경력/학력/고용형태)
        cond_spans = [s.get_text(" ", strip=True) for s in item.select(".job_condition span")]
        location, career, edu, emptype = _classify_conditions(cond_spans)

        # 직무 카테고리
        sector = item.select_one(".job_sector")
        job_category = ""
        if sector:
            job_category = re.sub(r"\s+", " ", sector.get_text(", ", strip=True))
            job_category = re.sub(r",?\s*(등록일|수정일).*$", "", job_category).strip(" ,")

        # 등록/수정일
        item_text = item.get_text(" ", strip=True)
        reg_date, date_type = "", ""
        m = DATE_RE.search(item_text)
        if m:
            date_type = m.group(1)
            yy, mm, dd = int(m.group(2)), int(m.group(3)), int(m.group(4))
            try:
                reg_date = date(2000 + yy, mm, dd).strftime("%Y-%m-%d")
            except ValueError:
                reg_date = ""

        # 마감일
        dm = DEADLINE_RE.search(item_text)
        deadline = dm.group(1).replace(" ", "") if dm else ""

        jobs.append({
            "rec_idx": rid,
            "키워드": keyword,
            "수집일시": now,
            "등록일": reg_date,
            "날짜구분": date_type,           # '등록일' 또는 '수정일'
            "기업명": company,
            "공고제목": title,
            "직무카테고리": job_category,
            "근무지역": location,
            "경력": career,
            "학력": edu,
            "고용형태": emptype,
            "마감일": deadline,
            "공고링크": f"{BASE}/zf_user/jobs/relay/view?rec_idx={rid}",
        })

    return jobs, True


# ===========================================================================
# 4) 키워드 하나에 대해 전체 페이지 수집
# ===========================================================================
def scrape_keyword(session, keyword, seen_ids, now):
    print(f"\n=== '{keyword}' 수집 시작 ===")
    collected, page = [], 1
    while True:
        params = f"searchword={quote(keyword)}&recruitPage={page}"
        if EXTRA_PARAMS:
            params += "&" + EXTRA_PARAMS.lstrip("?&")
        url = f"{SEARCH_URL}?{params}"

        html = fetch(session, url)
        if html is None:
            print(f"  [x] {page}페이지 실패 → 중단")
            break

        jobs, has_results = parse_page(html, keyword, now)
        if not has_results or not jobs:
            print(f"  - {page}페이지: 결과 없음 → 종료")
            break

        new_count = 0
        for j in jobs:
            if j["rec_idx"] not in seen_ids:     # 전역 중복 제거(첫 키워드/첫 데이터 우선)
                seen_ids.add(j["rec_idx"])
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
# 5) 최근 1개월 필터 / 메인 파일 로드·저장
# ===========================================================================
def is_recent(row, cutoff):
    """등록일(수정일)이 cutoff 이후면 True. 날짜 파싱 실패 시 안전하게 유지(True)."""
    d = row.get("등록일", "")
    if not d:
        return True
    try:
        return datetime.strptime(d, "%Y-%m-%d").date() >= cutoff
    except ValueError:
        return True


def load_existing(path):
    rows, ids = [], set()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                rows.append(row)
                if row.get("rec_idx"):
                    ids.add(row["rec_idx"])
        print(f"[로드] 기존 메인 파일 {len(rows)}건")
    else:
        print("[로드] 기존 메인 파일 없음 → 새로 생성")
    return rows, ids


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
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cutoff = date.today() - timedelta(days=RECENT_DAYS)

    session = requests.Session()
    existing_rows, seen_ids = load_existing(MAIN_CSV)

    new_rows = []
    for kw in KEYWORDS:
        new_rows.extend(scrape_keyword(session, kw, seen_ids, now))
        time.sleep(random.uniform(*DELAY_RANGE))

    # 최근 1개월 필터 (등록일/수정일 기준)
    before = len(new_rows)
    new_rows = [r for r in new_rows if is_recent(r, cutoff)]
    print(f"[기간필터] {before}건 → {len(new_rows)}건 (최근 {RECENT_DAYS}일, 기준일 {cutoff})")

    all_rows = existing_rows + new_rows
    all_rows, removed = prune_old(all_rows, RETENTION_DAYS)   # 수집 60일 초과 자동 삭제
    print(f"\n########## 신규 {len(new_rows)}건 / 삭제 {removed}건 / 전체 {len(all_rows)}건 ##########")
    save_main(MAIN_CSV, all_rows)


if __name__ == "__main__":
    main()
