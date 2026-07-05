import requests
from bs4 import BeautifulSoup
import time
import config
import telegram_logger

# 🕵️‍♂️ 로봇이 아닌 '진짜 사람 브라우저'처럼 보이기 위한 변장 마스크입니다.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
}

def fetch_jobkorea():
    """
    1. 잡코리아에서 검색어와 기업 조건에 맞춰 공고를 긁어오는 함수
    """
    jobs = []
    
    # config.py에서 선택한 기업 형태에 맞춰 잡코리아 전용 검색 필터 주소를 만듭니다.
    company_filter = ""
    if config.CHOSEN_COMPANY_TYPE == "대기업":
        company_filter = "&st=1"
    elif config.CHOSEN_COMPANY_TYPE == "중견기업":
        company_filter = "&st=2"
    elif config.CHOSEN_COMPANY_TYPE == "외국계기업":
        company_filter = "&st=4"

    for keyword in config.KEYWORDS:
        url = f"https://www.jobkorea.co.kr/Search/?stext={keyword}{company_filter}&tabType=recruit"
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                post_items = soup.select(".list-post .post")
                
                for item in post_items:
                    comp_tag = item.select_one(".name")
                    title_tag = item.select_one(".title")
                    
                    if comp_tag and title_tag:
                        comp_name = comp_tag.get_text(strip=True)
                        title_text = title_tag.get_text(strip=True)
                        
                        link = title_tag.get("href", "")
                        if link and not link.startswith("http"):
                            link = f"https://www.jobkorea.co.kr{link}"
                            
                        option_tag = item.select_one(".option")
                        option_text = option_tag.get_text(" ", strip=True) if option_tag else "정보 없음"
                        
                        jobs.append({
                            "site": "잡코리아",
                            "company": comp_name,
                            "title": title_text,
                            "url": link,
                            "location": option_text.split(" ")[0] if option_text else "지역 미정",
                            "experience": "조건 만족 (필터링 수집)"
                        })
            else:
                print(f"❌ [잡코리아] 페이지 접근 실패 (코드: {response.status_code})")
                
            time.sleep(1)
            
        except Exception as e:
            telegram_logger.log_error("fetch_scraper.py (잡코리아 크롤링 중)", e)
            
    print(f"✅ [잡코리아] 총 {len(jobs)}개의 공고를 크롤링했습니다.")
    return jobs


def fetch_peoplenjob():
    """
    2. ★새로 추가됨★ 피플앤잡에서 검색어에 맞춰 공고를 긁어오는 함수
    (피플앤잡은 사이트 특성상 99%가 외국계/대기업 공고이므로 키워드로만 타겟팅합니다)
    """
    jobs = []
    
    for keyword in config.KEYWORDS:
        # 피플앤잡 채용공고 검색 주소
        url = f"https://www.peoplenjob.com/jobs?q={keyword}"
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                
                # 채용 공고가 들어있는 테이블의 행(row)들을 선택합니다.
                job_rows = soup.select("table.job-list-table tbody tr")
                
                for row in job_rows:
                    # 광고나 빈 행은 건너뜁니다.
                    if "premium-job" in row.get("class", []) or not row.select_one(".job-title"):
                        continue
                        
                    title_tag = row.select_one(".job-title a")
                    comp_tag = row.select_one(".company-name")
                    loc_tag = row.select_one(".location")
                    
                    if title_tag and comp_tag:
                        title_text = title_tag.get_text(strip=True)
                        comp_name = comp_tag.get_text(strip=True)
                        location = loc_tag.get_text(strip=True) if loc_tag else "지역 미정"
                        
                        # 상세 링크 주소 조립
                        link = title_tag.get("href", "")
                        if link and not link.startswith("http"):
                            link = f"https://www.peoplenjob.com{link}"
                            
                        jobs.append({
                            "site": "피플앤잡",
                            "company": comp_name,
                            "title": title_text,
                            "url": link,
                            "location": location,
                            "experience": "외국계/대기업 중심 공고"
                        })
            else:
                print(f"❌ [피플앤잡] 페이지 접근 실패 (코드: {response.status_code})")
                
            time.sleep(1)
            
        except Exception as e:
            telegram_logger.log_error("fetch_scraper.py (피플앤잡 크롤링 중)", e)
            
    print(f"✅ [피플앤잡] 총 {len(jobs)}개의 공고를 크롤링했습니다.")
    return jobs


def run_scraper_collection():
    """
    크롤링 팀(잡코리아, 피플앤잡)의 데이터를 모두 모아서 리스트로 합쳐주는 총괄 함수
    """
    print("🚀 웹 크롤러 기반 채용공고 수집을 시작합니다...")
    scraped_jobs = []
    
    scraped_jobs.extend(fetch_jobkorea())
    scraped_jobs.extend(fetch_peoplenjob())  # 인디드 대신 피플앤잡 호출
    
    print(f"🏁 [크롤러 수집 완료] 총 {len(scraped_jobs)}개의 공고가 모였습니다.")
    return scraped_jobs


if __name__ == "__main__":
    # 개별 테스트용 코드
    run_scraper_collection()
