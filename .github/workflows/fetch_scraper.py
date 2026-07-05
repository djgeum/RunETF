import os
import sys
import requests
from bs4 import BeautifulSoup

# =====================================================================
# [경로 보정] 혹시 모를 모듈 호출 에러 방지용 시스템
# =====================================================================
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)


def scrape_jobs():
    """
    채용 사이트의 웹 페이지를 직접 크롤링/스크래핑하여 신규 채용 정보를 수집합니다.
    """
    print("🌐 [웹 스크래핑 엔진] 가동 시작...")
    scraped_results = []
    
    # AI 비서의 맞춤형 탐색 키워드
    keywords = ["해외영업", "화장품", "마케팅"]
    
    # -----------------------------------------------------------------
    # 예시: 사람인 검색 페이지 스크래핑 구조
    # (실제 사람인 서버 정책 및 구조 변경에 대비하여 안전하게 예외처리 적용)
    # -----------------------------------------------------------------
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    for keyword in keywords:
        print(f"🔎 웹 스크래핑으로 '{keyword}' 관련 공고 탐색 중...")
        
        # 사람인 검색 결과 URL (예시 경로)
        search_url = f"https://www.saramin.co.kr/zf_user/search/recruit?searchword={keyword}"
        
        try:
            response = requests.get(search_url, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"⚠️ {keyword} 스크래핑 건너넙니다 (상태 코드: {response.status_code})")
                continue
                
            soup = BeautifulSoup(response.text, "html.parser")
            
            # 사람인 공고 목록 영역 선택 (사이트 구조에 맞는 셀렉터 예시)
            job_listings = soup.select(".item_recruit")
            
            for item in job_listings[:5]:  # 과도한 트래픽 방지를 위해 키워드당 최신 5개씩만 수집
                try:
                    # 제목, 회사명, 링크 추출
                    title_element = item.select_one(".job_tit a")
                    corp_element = item.select_one(".corp_name a")
                    
                    if title_element and corp_element:
                        title = title_element.get_text(strip=True)
                        corp = corp_element.get_text(strip=True)
                        link = "https://www.saramin.co.kr" + title_element["href"]
                        
                        # 조건 정보 (경력, 학력, 근무지 등)
                        conditions = [span.get_text(strip=True) for span in item.select(".job_condition span")]
                        condition_txt = ", ".join(conditions) if conditions else "정보 없음"
                        
                        scraped_results.append({
                            "site": "사람인(웹)",
                            "company": corp,
                            "title": title,
                            "url": link,
                            "info": f"조건: {condition_txt} / 키워드: {keyword}"
                        })
                except Exception as item_e:
                    print(f"⚠️ 개별 공고 파싱 중 에러 발생 (무시하고 진행): {item_e}")
                    continue
                    
        except Exception as e:
            print(f"❌ '{keyword}' 스크래핑 중 오류 발생: {e}")
            continue

    print(f"✅ 웹 스크래핑 완료! 총 {len(scraped_results)}건 수집됨.")
    return scraped_results


if __name__ == "__main__":
    # 단독 테스트 실행용
    results = scrape_jobs()
    for r in results[:3]:
        print(r)
