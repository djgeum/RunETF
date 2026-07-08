import os
import sys
import requests
import pandas as pd  # 엑셀을 읽기 위한 핵심 도구
from bs4 import BeautifulSoup

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

def load_target_companies():
    """target_companies.xlsx 파일에서 '기업명' 열의 회사 리스트를 읽어옵니다."""
    excel_path = os.path.join(current_dir, "target_companies.xlsx")
    if not os.path.exists(excel_path):
        print("ℹ️ [엑셀 엔진] target_companies.xlsx 파일이 없어 타겟 기업 수집을 건너넙니다.")
        return []
    try:
        df = pd.read_excel(excel_path)
        if "기업명" in df.columns:
            # 공백을 제거하고 유효한 기업명만 리스트로 만듭니다.
            companies = df["기업명"].dropna().astype(str).str.strip().tolist()
            print(f"📂 [엑셀 엔진] 성공적으로 {len(companies)}개의 타겟 기업을 로드했습니다.")
            return companies
        else:
            print("⚠️ [엑셀 엔진] 엑셀 파일에 '기업명' 열(Column)이 존재하지 않습니다.")
            return []
    except Exception as e:
        print(f"❌ [엑셀 엔진] 엑셀 파일을 읽는 중 오류 발생: {e}")
        return []

def scrape_jobs():
    """기존 키워드 수집과 엑셀 타겟 기업들의 채용 공고를 함께 수집합니다."""
    print("🌐 [웹 스크래핑 엔진] 가동 시작...")
    scraped_results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # 1. 기존 직무/산업 키워드 기반 탐색
    keywords = ["해외영업", "화장품", "마케팅"]
    for keyword in keywords:
        print(f"🔎 직무 키워드 '{keyword}' 관련 공고 탐색 중...")
        search_url = f"https://www.saramin.co.kr/zf_user/search/recruit?searchword={keyword}"
        scraped_results.extend(_parse_saramin(search_url, headers, f"키워드: {keyword}"))

    # 2. 🔥 [새 기능] 엑셀 타겟 기업 기반 무조건 탐색
    target_companies = load_target_companies()
    for company in target_companies:
        print(f"🎯 타겟 기업 무조건 수집: '{company}' 공고 검색 중...")
        # 사람인에서 회사명으로 정밀 검색하는 URL
        search_url = f"https://www.saramin.co.kr/zf_user/search/recruit?searchword={company}"
        # 타겟 기업 공고는 정보창에 [★타겟기업] 마크를 달아줍니다.
        scraped_results.extend(_parse_saramin(search_url, headers, f"[★타겟기업] {company}"))

    print(f"✅ 웹 스크래핑 완료! 총 {len(scraped_results)}건 수집됨 (중복 포함).")
    return scraped_results

def _parse_saramin(url, headers, source_tag):
    """사람인 페이지를 파싱하는 내부 공통 함수"""
    results = []
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return results
        soup = BeautifulSoup(response.text, "html.parser")
        job_listings = soup.select(".item_recruit")
        
        for item in job_listings[:3]:  # 속도와 차단 방지를 위해 최대 3개씩만
            title_element = item.select_one(".job_tit a")
            corp_element = item.select_one(".corp_name a")
            
            if title_element and corp_element:
                title = title_element.get_text(strip=True)
                corp = corp_element.get_text(strip=True)
                link = "https://www.saramin.co.kr" + title_element["href"]
                
                conditions = [span.get_text(strip=True) for span in item.select(".job_condition span")]
                condition_txt = ", ".join(conditions) if conditions else "정보 없음"
                
                results.append({
                    "site": "사람인(웹)",
                    "company": corp,
                    "title": title,
                    "url": link,
                    "info": f"조건: {condition_txt} / 태그: {source_tag}"
                })
    except Exception as e:
        print(f"⚠️ 파싱 중 에러 발생 (스킵): {e}")
    return results
