import os
import sys
import requests

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    import config
except ImportError:
    class DummyConfig:
        # 💡 [스마트 그물망 전략] 직무명이 아닌 '글로벌/비즈니스 속성' 키워드로 넓게 탐색
        KEYWORDS = ["글로벌", "해외", "Global", "사업개발", "외국계"]
        SARAMIN_KEY = os.getenv("SARAMIN_KEY")
        GOYONG_KEY = os.getenv("GOYONG_KEY")
        
        # 💡 키워드당 수집량을 늘려 충분한 모수를 확보 (AI가 이 중에서 옥석을 가려냅니다)
        MAX_JOBS_PER_KEYWORD = 30 
        HTTP_HEADERS = {"User-Agent": "Mozilla/5.0"}
    config = DummyConfig()


def get_jobs():
    """
    사람인 오픈 API를 호출하여 최신 채용 공고를 수집합니다.
    반환값: (수집된 공고 리스트, 진단 로그 리스트)
    """
    print("🔌 [오픈 API 엔진] 스마트 그물망 가동 시작...")
    api_results = []
    diag = []  # 진단 로그
    seen_urls = set() # 💡 중복 수집 방지를 위한 URL 저장소

    count = getattr(config, "MAX_JOBS_PER_KEYWORD", 30)
    headers = getattr(config, "HTTP_HEADERS", {"User-Agent": "Mozilla/5.0"})

    # -----------------------------------------------------------------
    # 1. 사람인 채용공고 오픈 API
    # -----------------------------------------------------------------
    if config.SARAMIN_KEY:
        diag.append("🔑 사람인 API 키 감지됨 → 요청 시작")
        for keyword in config.KEYWORDS:
            url = "https://oapi.saramin.co.kr/job-search"
            
            # API 파라미터 설정
            params = {
                "access-key": config.SARAMIN_KEY,
                "keywords": keyword,
                "count": count,
                "sort": "pd", # 💡 pd(Publish Date): 최신순 정렬 (이미 본 옛날 공고 방지)
                "job_type": "1,2", # 1: 정규직, 2: 계약직
            }
            
            try:
                response = requests.get(url, params=params, headers=headers, timeout=10)
                status = response.status_code
                body_len = len(response.text)

                if status != 200:
                    diag.append(
                        f"⚠️ 사람인API '{keyword}' 실패 status={status}, "
                        f"len={body_len}, body[:120]={response.text[:120]!r}"
                    )
                    continue

                try:
                    data = response.json()
                except Exception as je:
                    diag.append(f"⚠️ 사람인API '{keyword}' JSON 파싱 실패: {je}")
                    continue

                jobs_list = data.get("jobs", {}).get("job", [])
                if isinstance(jobs_list, dict):
                    jobs_list = [jobs_list]

                before = len(api_results)
                for job in jobs_list:
                    job_url = job.get("url", "")
                    
                    # 💡 중복 제거 로직: 이미 수집된 공고(URL 기준)는 패스
                    if not job_url or job_url in seen_urls:
                        continue
                    seen_urls.add(job_url)

                    # 💡 안전한 파싱 로직: 데이터가 비어있어도 에러 없이 대체 텍스트 삽입
                    company_dict = job.get("company", {})
                    company_name = company_dict.get("detail", {}).get("name") or company_dict.get("name") or "회사명 미상"

                    position_dict = job.get("position", {})
                    title = position_dict.get("title") or "공고 제목 없음"
                    
                    loc_data = position_dict.get("location", {})
                    location = loc_data.get("name", "") if isinstance(loc_data, dict) else str(loc_data)

                    exp_data = position_dict.get("experience-level", {})
                    experience = exp_data.get("name", "경력무관") if isinstance(exp_data, dict) else str(exp_data)

                    api_results.append({
                        "site": "사람인",
                        "company": company_name,
                        "title": title,
                        "url": job_url,
                        "info": f"경력: {experience} | 지역: {location} | 키워드: {keyword}",
                    })
                    
                added = len(api_results) - before
                diag.append(f"✅ 사람인API '{keyword}' 검색 완료: 신규 {added}건 추가")
                
            except Exception as e:
                diag.append(f"❌ 사람인API '{keyword}' 네트워크/실행 예외: {e}")
    else:
        diag.append("💡 SARAMIN_KEY 없음 → 사람인 API 생략")

    # -----------------------------------------------------------------
    # 2. 고용노동부 워크넷 API (생략)
    # -----------------------------------------------------------------
    if config.GOYONG_KEY:
        diag.append("🔑 GOYONG_KEY 감지됨 → 워크넷 API 호출 코드는 미구현 (스크래핑에 집중)")

    print(f"✅ 오픈 API 수집 완료! 총 {len(api_results)}건의 유니크 공고 확보")
    return api_results, diag


if __name__ == "__main__":
    results, diag = get_jobs()
    print("\n--- 진단 로그 ---")
    for line in diag:
        print(line)
    print(f"\n총 {len(results)}건 수집됨")
    for r in results[:5]:  # 상위 5개만 샘플 출력
        print(r)
