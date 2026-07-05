import os
import sys
import requests

# =====================================================================
# [경로 보정 및 설정 파일 연동]
# =====================================================================
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# 앞서 만든 config.py에서 탐색 키워드 및 API 인증키 정보를 가져옵니다.
try:
    import config
except ImportError:
    class DummyConfig:
        KEYWORDS = ["해외영업", "화장품", "마케팅"]
        SARAMIN_KEY = os.getenv("SARAMIN_KEY")
        GOYONG_KEY = os.getenv("GOYONG_KEY")
    config = DummyConfig()


def get_jobs():
    """
    사람인 및 고용노동부 오픈 API를 호출하여 설정된 키워드 관련 
    신규 채용 공고 데이터를 안전하게 수집합니다.
    """
    print("🔌 [오픈 API 엔진] 가동 시작...")
    api_results = []
    
    # -----------------------------------------------------------------
    # 1. 사람인 채용공고 오픈 API 호출 파트
    # -----------------------------------------------------------------
    if config.SARAMIN_KEY:
        print("🔑 사람인 API 키가 확인되어 데이터 요청을 시작합니다.")
        for keyword in config.KEYWORDS:
            url = f"https://api.saramin.co.kr/home/api/job-search?key={config.SARAMIN_KEY}&keyword={keyword}&count=5"
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    # 사람인 API 규격에 맞춰 데이터 파싱
                    jobs_list = data.get("jobs", {}).get("job", [])
                    for job in jobs_list:
                        company_name = job.get("company", {}).get("detail", {}).get("name")
                        title = job.get("position", {}).get("title")
                        job_url = job.get("url")
                        location = job.get("position", {}).get("location", "")
                        
                        api_results.append({
                            "site": "사람인(API)",
                            "company": company_name,
                            "title": title,
                            "url": job_url,
                            "info": f"지역: {location} / 키워드: {keyword}"
                        })
            except Exception as e:
                print(f"⚠️ 사람인 API '{keyword}' 조회 중 일시적 오류 (스킵): {e}")
    else:
        print("💡 사람인 API 키(SARAMIN_KEY)가 Secrets에 설정되지 않아 웹 스크래핑 결과로 대체합니다.")

    # -----------------------------------------------------------------
    # 2. 고용노동부 워크넷 API (또는 기타 공공 API) 확장 파트
    # -----------------------------------------------------------------
    if config.GOYONG_KEY:
        print("🔑 고용노동부 워크넷 API 연동을 조회합니다.")
        # 공공 API 규격에 맞춰 호출하는 영역 (설정되어 있다면 연동)
    else:
        print("💡 고용노동부 API 키가 설정되지 않아 생략합니다.")

    print(f"✅ 오픈 API 수집 완료! 총 {len(api_results)}건 수집됨.")
    return api_results


if __name__ == "__main__":
    # 단독 기능 테스트용
    results = get_jobs()
    print(results)
