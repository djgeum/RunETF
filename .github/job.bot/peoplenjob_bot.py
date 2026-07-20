# -*- coding: utf-8 -*-
"""
peoplenjob_bot.py
피플앤잡(외국기업 취업) 키워드 검색 수집 봇  (Playwright 기반)
 
방식
  - 8개 키워드를 순서대로 URL 검색: /jobs?q=키워드&field=all[&career_level=..]&page=N
    (피플앤잡은 q 만으로는 검색이 안 먹고 field 를 함께 줘야 작동)
  - 각 카드(div.jd-card): 제목·회사명·근무지역·경력레벨·등록일·마감일·링크(rec_id)
  - 등록일 최신순 정렬 → 최근 RECENT_DAYS 를 넘어서면 조기 중단
  - rec_id 중복 제거(첫 키워드/첫 데이터 우선)
  - ★ 제목에 EXCLUDE_TITLE_WORDS(예: '계약직')가 들어간 공고는 아예 저장하지 않음
  - 재실행 시 기존 파일에 신규만 누적
 
설치
    py -3.13 -m pip install playwright
    py -3.13 -m playwright install chromium
실행
    py -3.13 peoplenjob_bot.py
"""
 
import os
import csv
import time
import random
from datetime import datetime, date, timedelta
from urllib.parse import quote
 
from playwright.sync_api import sync_playwright
 
# ===========================================================================
# 1) 설정
# ===========================================================================
BASE = "https://www.peoplenjob.com"
 
# 검색 키워드 (이 순서가 중복 공고의 '첫 키워드' 우선순위)
KEYWORDS = ["마케팅", "해외영업", "신입", "공채", "글로벌", "marketing", "MD", "브랜드"]
 
# 검색 범위: all(전체) / title(제목) / company(회사명) 등
SEARCH_FIELD = "all"
 
# 직급 필터: "" = 전 직급, "1" = 인턴.신입.2년이내 (2~6이 사원/대리과장/팀장부장/임원/CEO)
CAREER_LEVEL = "1"
 
# ★ 제목에 이 단어가 있으면 저장 제외 (대소문자 무시, 원하는 만큼 추가)
EXCLUDE_TITLE_WORDS = [
    "계약직",
    "6개월 전환형",
    "Assistant",
    "아르바이트",
    "경력 2년 이상",
    "경력 3년 이상",
    "경력 4년 이상",
    "경력 5년 이상",
    "디자이너",
]
 
# 최근 N일 이내 등록만 (1개월 = 31). 최신순 정렬이라 넘어서면 조기 중단.
RECENT_DAYS = 31
 
MAIN_CSV = "peoplenjob_list.csv"
 
# 안전장치: 키워드당 최대 페이지 (0 = 무제한)
MAX_PAGES = 100
 
# 수집일(수집일시) 기준 이 일수를 넘은 공고는 저장 시 자동 삭제
RETENTION_DAYS = 60
 
DELAY_RANGE = (1.0, 2.2)
HEADLESS = True            # 차단되면 False 로
 
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
 
# 잡코리아 list.csv 와 동일한 컬럼 형식
FIELDS = [
    "job_id", "키워드", "수집일시", "등록일", "기업명", "공고제목",
    "직무카테고리", "근무지역", "경력", "학력", "마감일", "공고링크",
]
 
 
# ===========================================================================
# 2) 유틸
# ===========================================================================
def parse_mmdd(text, today):
    """'07.19 ~' / '07.19' -> date. 연도는 오늘 기준 추론(미래면 작년)."""
    import re
    if not text:
        return None
    m = re.search(r"(\d{1,2})\.(\d{1,2})", text)
    if not m:
        return None
    mm, dd = int(m.group(1)), int(m.group(2))
    try:
        d = date(today.year, mm, dd)
    except ValueError:
        return None
    if d > today + timedelta(days=1):
        d = date(today.year - 1, mm, dd)
    return d
 
 
def is_excluded(title):
    """제목에 제외 단어가 하나라도 있으면 True (대소문자 무시)."""
    t = (title or "").lower()
    return any(w and w.lower() in t for w in EXCLUDE_TITLE_WORDS)
 
 
def build_url(keyword, page):
    params = f"q={quote(keyword)}&field={SEARCH_FIELD}&page={page}"
    if CAREER_LEVEL:
        params += f"&career_level={CAREER_LEVEL}"
    return f"{BASE}/jobs?{params}"
 
 
# ===========================================================================
# 3) 카드 추출 JS
# ===========================================================================
EXTRACT_JS = r"""
() => Array.from(document.querySelectorAll('div.jd-card')).map(card => {
  const q = s => { const e = card.querySelector(s); return e ? e.textContent.trim() : ''; };
  const a = card.querySelector('a[href*="/jobs/"]');
  const href = a ? a.getAttribute('href') : '';
  const m = href.match(/\/jobs\/(\d+)/);
  return {
    rec_id: m ? m[1] : '',
    title: q('h5.jd-card-title a') || q('h5.jd-card-title'),
    company: q('a.jd-card-company'),
    location: q('span.jd-card-meta-location-text'),
    career: q('span.jd-card-meta-career-text'),
    reg: q('span.jd-card-meta-static'),
    deadline: q('span.job-fin-date'),
    href: href
  };
})
"""
 
 
# ===========================================================================
# 4) 키워드 하나 수집
# ===========================================================================
def scrape_keyword(page, keyword, seen_ids, now, today, cutoff):
    print(f"\n=== '{keyword}' 수집 시작 ===")
    collected = []
    excluded_total = 0
    for p in range(1, (MAX_PAGES or 10 ** 9) + 1):
        url = build_url(keyword, p)
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_selector("div.jd-card", timeout=15000)
        except Exception as e:
            print(f"  [!] {p}페이지 로드 실패/카드 없음 → 종료 ({e})")
            break
 
        cards = page.evaluate(EXTRACT_JS)
        if not cards:
            print(f"  - {p}페이지: 카드 없음 → 종료")
            break
 
        new_cnt = old_cnt = exc_cnt = 0
        for c in cards:
            rid = c.get("rec_id")
            if not rid:
                continue
            reg_date = parse_mmdd(c.get("reg", ""), today)
            if reg_date and reg_date < cutoff:      # 기간 밖
                old_cnt += 1
                continue
            title = c.get("title", "")
            if is_excluded(title):                  # ★ 제외 단어 → 저장 안 함
                exc_cnt += 1
                continue
            if rid in seen_ids:                     # 중복(다른 키워드 포함)
                continue
 
            seen_ids.add(rid)
            collected.append({
                "job_id": rid,
                "키워드": keyword,
                "수집일시": now,
                "등록일": reg_date.strftime("%Y-%m-%d") if reg_date else "",
                "기업명": c.get("company", ""),
                "공고제목": title,
                "직무카테고리": "",                 # 피플앤잡 키워드검색 목록엔 직무카테고리 표기 없음
                "근무지역": c.get("location", ""),
                "경력": c.get("career", ""),         # 피플앤잡 경력레벨(인턴.신입/사원/대리.과장 등)
                "학력": "",                          # 목록에 학력 표기 없음
                "마감일": c.get("deadline", ""),
                "공고링크": f"{BASE}/jobs/{rid}",
            })
            new_cnt += 1
 
        excluded_total += exc_cnt
        print(f"  - {p}p: {len(cards)}건 / 신규 {new_cnt} / 제외 {exc_cnt} / 기간밖 {old_cnt} (누적 {len(collected)})")
 
        if old_cnt > 0:                              # 최신순 → 경계 도달
            print("  - 최근 1개월 경계 도달 → 조기 중단")
            break
        time.sleep(random.uniform(*DELAY_RANGE))
 
    print(f"=== '{keyword}' 완료: {len(collected)}건 (제외 {excluded_total}건) ===")
    return collected
 
 
# ===========================================================================
# 5) 메인 파일 로드/저장
# ===========================================================================
def load_existing(path):
    rows, ids = [], set()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                rows.append(row)
                if row.get("job_id"):
                    ids.add(row["job_id"])
        print(f"[로드] 기존 {len(rows)}건")
    else:
        print("[로드] 기존 파일 없음 → 새로 생성")
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
    today = date.today()
    cutoff = today - timedelta(days=RECENT_DAYS)
 
    existing_rows, seen_ids = load_existing(MAIN_CSV)
    print(f"제외 단어: {EXCLUDE_TITLE_WORDS} / 검색범위: {SEARCH_FIELD} / 직급: {CAREER_LEVEL or '전체'}")
 
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=HEADLESS)
        context = browser.new_context(user_agent=USER_AGENT, locale="ko-KR")
        page = context.new_page()
        new_rows = []
        for kw in KEYWORDS:
            new_rows.extend(scrape_keyword(page, kw, seen_ids, now, today, cutoff))
            time.sleep(random.uniform(*DELAY_RANGE))
        browser.close()
 
    all_rows = existing_rows + new_rows
    all_rows, removed = prune_old(all_rows, RETENTION_DAYS)   # 수집 60일 초과 자동 삭제
    print(f"\n########## 신규 {len(new_rows)}건 / 삭제 {removed}건 / 전체 {len(all_rows)}건 ##########")
    save_main(MAIN_CSV, all_rows)
 
 
if __name__ == "__main__":
    main()
