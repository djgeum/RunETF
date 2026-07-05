import os
import sys
import requests
from bs4 import BeautifulSoup

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    import config
except ImportError:
    class DummyConfig:
        KEYWORDS = ["해외영업", "화장품", "마케팅"]
        MAX_JOBS_PER_KEYWORD = 5
        HTTP_HEADERS = {"User-Agent": "Mozilla/5.0"}
    config = DummyConfig()


# 사람인 구조 변경에 대비한 '목록 컨테이너' 셀렉터 후보들 (위에서부터 순서대로 시도)
LIST_SELECTORS = [
    ".item_recruit",
    ".list_item",
    ".box_item",
    "div[class*='item_recruit']",
    "div[class*='list_item']",
]


def _extract_item(item, keyword):
    """한 공고 블록에서 제목/회사/링크/조건을 여러 셀렉터 후보로 추출."""
    title_el = (
        item.select_one(".job_tit a")
        or item.select_one("a[class*='job_tit']")
        or item.select_one("h2 a")
        or item.select_one("a[title]")
    )
    corp_el = (
        item.select_one(".corp_name a")
        or item.select_one("a[class*='corp_name']")
        or item.select_one("[class*='company'] a")
        or item.select_one("[class*='corp']")
    )
    if not title_el:
        return None

    title = title_el.get_text(strip=True) or title_el.get("title", "").strip()
    corp = corp_el.get_text(strip=True) if corp_el else "회사명 미상"

    href = title_el.get("href", "")
    if href.startswith("http"):
        link = href
    else:
        link = "https://www.saramin.co.kr" + href

    conditions = [s.get_text(strip=True) for s in item.select(".job_condition span")]
    condition_txt = ", ".join(conditions) if conditions else "정보 없음"

    return {
        "site": "사람인(웹)",
        "company": corp,
        "title": title,
        "url": link,
        "info": f"조건: {condition_txt} / 키워드: {keyword}",
    }


def scrape_jobs():
    """
    사람인 검색 페이지를 스크래핑합니다.
    반환값: (수집된 공고 리스트, 진단 로그 리스트)
    """
    print("🌐 [웹 스크래핑 엔진] 가동 시작...")
    scraped_results = []
    diag = []

    limit = getattr(config, "MAX_JOBS_PER_KEYWORD", 5)
    headers = getattr(config, "HTTP_HEADERS", {"User-Agent": "Mozilla/5.0"})
    keywords = config.KEYWORDS

    for keyword in keywords:
        # requests가 한글을 자동 인코딩하도록 params로 전달
        base = "https://www.saramin.co.kr/zf_user/search/recruit"
        params = {"searchword": keyword, "recruitPage": 1}

        try:
            response = requests.get(base, params=params, headers=headers, timeout=10)
            status = response.status_code
            html = response.text
            body_len = len(html)

            if status != 200:
                diag.append(
                    f"⚠️ 스크래핑 '{keyword}' status={status}, len={body_len} → 건너뜀"
                )
                continue

            # 차단/캡차/로그인유도 페이지 자동 감지
            lowered = html.lower()
            if any(w in lowered for w in ["captcha", "비정상", "접근이 차단", "robot"]):
                diag.append(
                    f"🚫 스크래핑 '{keyword}' 차단/캡차 의심 (status=200, len={body_len})"
                )
                continue

            soup = BeautifulSoup(html, "html.parser")

            # 여러 셀렉터 후보를 순서대로 시도
            job_listings = []
            used_selector = None
            for sel in LIST_SELECTORS:
                found = soup.select(sel)
                if found:
                    job_listings = found
                    used_selector = sel
                    break

            if not job_listings:
                # 200인데 목록 0개 → 구조 변경 또는 JS렌더링 의심. 근거를 남김.
                diag.append(
                    f"❓ 스크래핑 '{keyword}' status=200, len={body_len}, "
                    f"매칭 셀렉터 없음 → 사이트 구조변경/JS렌더링 의심"
                )
                continue

            before = len(scraped_results)
            for item in job_listings[:limit]:
                try:
                    parsed = _extract_item(item, keyword)
                    if parsed:
                        scraped_results.append(parsed)
                except Exception as item_e:
                    diag.append(f"⚠️ '{keyword}' 개별 파싱 에러(무시): {item_e}")
                    continue

            added = len(scraped_results) - before
            diag.append(
                f"✅ 스크래핑 '{keyword}' status=200, 셀렉터='{used_selector}', "
                f"목록={len(job_listings)}개, 수집={added}건"
            )

        except Exception as e:
            diag.append(f"❌ 스크래핑 '{keyword}' 예외: {e}")
            continue

    print(f"✅ 웹 스크래핑 완료! 총 {len(scraped_results)}건")
    return scraped_results, diag


if __name__ == "__main__":
    results, diag = scrape_jobs()
    print("\n--- 진단 로그 ---")
    for line in diag:
        print(line)
    print(f"\n총 {len(results)}건")
    for r in results[:3]:
        print(r)
