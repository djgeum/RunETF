import os
import sys
import requests
from bs4 import BeautifulSoup

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# 브라우저인 척 위장하기 위한 강력한 헤더
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
}

def scrape_jobs():
    print("🕸️ [웹 스크래핑 엔진] 피플앤잡 & 원티드 스나이핑 시작...")
    web_results = []
    diag = []
    seen_urls = set()

    # =================================================================
    # 1. 피플앤잡 (PeoplenJob) - 외국계 타깃
    # =================================================================
    try:
        # q=글로벌, career=1(신입), career=2(경력 1~3년 미만) 등 활용 가능
        # 여기서는 가장 많이 올라오는 '해외', '마케팅' 키워드로 최신 1페이지만 타겟팅
        pj_keywords = ["글로벌", "마케팅"]
        
        for keyword in pj_keywords:
            # 피플앤잡 검색 URL (최신순 정렬)
            url = f"https://www.peoplenjob.com/jobs?q={keyword}"
            response = requests.get(url, headers=HEADERS, timeout=10)
            
            if response.status_code != 200:
                diag.append(f"⚠️ 피플앤잡 '{keyword}' 접근 실패: {response.status_code}")
                continue
                
            soup = BeautifulSoup(response.text, 'html.parser')
            # 공고 리스트 추출 (클래스명 job-item을 가진 tr 태그 등)
            job_rows = soup.select("table.job-list tbody tr")
            
            added = 0
            for row in job_rows:
                title_tag = row.select_one(".job-title a")
                company_tag = row.select_one(".name a")
                
                if not title_tag or not company_tag:
                    continue
                    
                title = title_tag.text.strip()
                company = company_tag.text.strip()
                link = "https://www.peoplenjob.com" + title_tag['href']
                
                if link in seen_urls:
                    continue
                    
                seen_urls.add(link)
                web_results.append({
                    "site": "피플앤잡",
                    "company": company,
                    "title": title,
                    "url": link,
                    "info": f"키워드: {keyword} (외국계 중심)"
                })
                added += 1
                
            diag.append(f"✅ 피플앤잡 '{keyword}' 스크래핑 완료: {added}건 수집")
            
    except Exception as e:
        diag.append(f"❌ 피플앤잡 스크래핑 중 에러 발생: {e}")

    # =================================================================
    # 2. 원티드 (Wanted) - 내부 API 직접 호출 (스타트업/IT/외국계)
    # =================================================================
    try:
        # 원티드 직군 코드: 518(마케팅), 523(기획/비즈니스), 524(영업)
        # years=0 (신입), years=1 (1년차)
        wanted_url = "https://www.wanted.co.kr/api/v4/jobs"
        params = {
            "country": "kr",
            "locations": "all",
            "years": "0",  # 최소 연차
            "years_max": "1", # 최대 연차
            "job_sort": "job.latest_order", # 최신순
            "tag_type_ids": "518", # 마케팅 직군 예시
            "limit": "20" # 딱 20개만
        }
        
        response = requests.get(wanted_url, params=params, headers=HEADERS, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            jobs = data.get("data", [])
            added = 0
            
            for job in jobs:
                company = job.get("company", {}).get("name", "회사명 미상")
                title = job.get("position", "제목 미상")
                job_id = job.get("id")
                link = f"https://www.wanted.co.kr/wd/{job_id}"
                
                if link in seen_urls:
                    continue
                    
                seen_urls.add(link)
                web_results.append({
                    "site": "원티드",
                    "company": company,
                    "title": title,
                    "url": link,
                    "info": "조건: 신입~1년차 | 마케팅/비즈니스 직군"
                })
                added += 1
                
            diag.append(f"✅ 원티드 API 스크래핑 완료: {added}건 수집")
        else:
            diag.append(f"⚠️ 원티드 접근 실패: {response.status_code}")
            
    except Exception as e:
        diag.append(f"❌ 원티드 스크래핑 중 에러 발생: {e}")

    print(f"✅ 웹 스크래핑 완료! 총 {len(web_results)}건 확보")
    return web_results, diag

if __name__ == "__main__":
    results, diag = scrape_jobs()
    print("\n--- 진단 로그 ---")
    for line in diag:
        print(line)
    print(f"\n총 {len(results)}건 수집됨")
    for r in results[:5]:
        print(r)
