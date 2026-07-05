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
        KEYWORDS = ["해외영업", "화장품", "마케팅"]
        SARAMIN_KEY = os.getenv("SARAMIN_KEY")
        GOYONG_KEY = os.getenv("GOYONG_KEY")
        MAX_JOBS_PER_KEYWORD = 5
        HTTP_HEADERS = {"User-Agent": "Mozilla/5.0"}
    config = DummyConfig()


def get_jobs():
    """
    사람인/고용노동부 오픈 API를 호출하여 채용 공고를 수집합니다.
    반환값: (수집된 공고 리스트, 진단 로그 리스트)
    """
    print("🔌 [오픈 API 엔진] 가동 시작...")
    api_results = []
    diag = []  # 진단 로그

    count = getattr(config, "MAX_JOBS_PER_KEYWORD", 5)
    headers = getattr(config, "HTTP_HEADERS", {"User-Agent": "Mozilla/5.0"})

    # -----------------------------------------------------------------
    # 1. 사람인 채용공고 오픈 API
    #    ✅ 공식 엔드포인트: https://oapi.saramin.co.kr/job-search
    #    ✅ 파라미터: access-key, keywords, count
    # -----------------------------------------------------------------
    if config.SARAMIN_KEY:
        diag.append("🔑 사람인 API 키 감지됨 → 요청 시작")
        for keyword in config.KEYWORDS:
            url = "https://oapi.saramin.co.kr/job-search"
            params = {
                "access-key": config.SARAMIN_KEY,
                "keywords": keyword,
                "count": count,
            }
            try:
                response = requests.get(url, params=params, headers=headers, timeout=10)
                status = response.status_code
                body_len = len(response.text)

                if status != 200:
                    # 응답 본문 앞부분을 함께 남겨서 원인(키 오류/차단 등) 파악
                    diag.append(
                        f"⚠️ 사람인API '{keyword}' 실패 status={status}, "
                        f"len={body_len}, body[:120]={response.text[:120]!r}"
                    )
                    continue

                try:
                    data = response.json()
                except Exception as je:
                    diag.append(
                        f"⚠️ 사람인API '{keyword}' JSON 파싱 실패: {je} / "
                        f"body[:120]={response.text[:120]!r}"
                    )
                    continue

                jobs_list = data.get("jobs", {}).get("job", [])
                # job이 단일 객체(dict)로 오는 경우 방어
                if isinstance(jobs_list, dict):
                    jobs_list = [jobs_list]

                before = len(api_results)
                for job in jobs_list:
                    company_name = (
                        job.get("company", {}).get("detail", {}).get("name")
                    )
                    title = job.get("position", {}).get("title")
                    job_url = job.get("url")
                    location = (
                        job.get("position", {})
                        .get("location", {})
                        .get("name", "")
                        if isinstance(job.get("position", {}).get("location"), dict)
                        else job.get("position", {}).get("location", "")
                    )
                    api_results.append({
                        "site": "사람인(API)",
                        "company": company_name,
                        "title": title,
                        "url": job_url,
                        "info": f"지역: {location} / 키워드: {keyword}",
                    })
                added = len(api_results) - before
                diag.append(
                    f"✅ 사람인API '{keyword}' status=200, "
                    f"응답 job수={len(jobs_list)}, 수집={added}건"
                )
            except Exception as e:
                diag.append(f"❌ 사람인API '{keyword}' 예외: {e}")
    else:
        diag.append("💡 SARAMIN_KEY 없음 → 사람인 API 생략 (스크래핑으로 대체)")

    # -----------------------------------------------------------------
    # 2. 고용노동부 워크넷 API (미구현 상태 명시)
    # -----------------------------------------------------------------
    if config.GOYONG_KEY:
        diag.append("🔑 GOYONG_KEY 감지됨 → 단, 워크넷 API 호출 코드는 아직 미구현")
    else:
        diag.append("💡 GOYONG_KEY 없음 → 워크넷 API 생략")

    print(f"✅ 오픈 API 수집 완료! 총 {len(api_results)}건")
    return api_results, diag


if __name__ == "__main__":
    results, diag = get_jobs()
    print("\n--- 진단 로그 ---")
    for line in diag:
        print(line)
    print(f"\n총 {len(results)}건")
    for r in results[:3]:
        print(r)
