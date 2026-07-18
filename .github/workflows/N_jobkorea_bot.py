import os
import sys
import json
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup

# =====================================================================
# [환경 세팅] 경로 고정 및 질문자님 전용 매칭 키워드 세팅
# =====================================================================
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# 1차 검문: 겉화면 공고 제목에서 거를 국내/외국계 분류별 키워드
KR_TITLE_KEYWORDS = ["마케팅", "해외영업", "신입", "공채", "글로벌", "marketing", "md", "브랜드"]
GLOBAL_TITLE_KEYWORDS = ["마케팅", "신입", "공채", "글로벌", "marketing", "brand"]

# 2차 검문: 상세 본문 텍스트 내에 포함되어야 할 직무 키워드
JOB_KEYWORDS = ["해외영업", "글로벌", "마케팅", "화장품", "영업", "sales", "global", "marketing"]


def load_target_companies():
    """target_companies.xlsx 파일에서 '기업명'과 '기업분류'를 함께 읽어옵니다."""
    excel_path = os.path.join(current_dir, "target_companies.xlsx")
    if not os.path.exists(excel_path):
        print("ℹ️ [잡코리아 봇] target_companies.xlsx 파일이 없어 종료합니다.")
        return []
    try:
        df = pd.read_excel(excel_path)
        # 필수 열 존재 여부 체크
        if "기업명" in df.columns and "기업분류" in df.columns:
            companies_data = []
            for _, row in df.iterrows():
                if pd.notna(row["기업명"]) and pd.notna(row["기업분류"]):
                    companies_data.append({
                        "name": str(row["기업명"]).strip(),
                        "type": str(row["기업분류"]).strip() # '국내' 또는 '외국'
                    })
            print(f"📂 [잡코리아 봇] 엑셀에서 {len(companies_data)}개의 분류된 기업 목록을 로드했습니다.")
            return companies_data
        else:
            print("⚠️ [잡코리아 봇] 엑셀에 '기업명' 또는 '기업분류' 열이 없습니다.")
            return []
    except Exception as e:
        print(f"❌ [잡코리아 봇] 엑셀 읽기 오류: {e}")
        return []

def deep_crawl_and_filter(url, headers):
    """[초고속 버전] 상세 페이지의 본문 텍스트만 0.1초 만에 스캔하고, 통이미지면 바로 수동 확인 태그를 달아 토스합니다."""
    try:
        time.sleep(0.5) # IP 차단 방지를 위한 최소한의 안전장치
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 잡코리아 상세 공고 iframe 추출
        iframe = soup.select_one("iframe#gib_frame")
        if iframe and iframe.has_attr("src"):
            iframe_src = iframe["src"]
            if not iframe_src.startswith("http"):
                iframe_src = "https://www.jobkorea.co.kr" + iframe_src
                
            iframe_res = requests.get(iframe_src, headers=headers, timeout=5)
            iframe_soup = BeautifulSoup(iframe_res.text, "html.parser")
            
            # 본문 텍스트 추출
            text_content = iframe_soup.get_text(strip=True)
            
            if len(text_content) > 150:
                # 글자가 충분하면 직무 키워드 2차 매칭
                if any(kw.lower() in text_content.lower() for kw in JOB_KEYWORDS):
                    return True, "본문 텍스트 매칭 성공"
                else:
                    return False, "직무 불일치 (본문 내용 무관)"
            else:
                # 🔥 [핵심 대책] 글자가 없고 통이미지인 경우 무거운 AI 구동 없이 바로 합격 처리하여 토스!
                return True, "통이미지 공고 (★수동 링크 확인 필요)"
                
        return True, "상세내용 파악 불가 (수동 확인 요망)"
        
    except Exception as e:
        print(f"   -> ⚠️ 상세 크롤링 에러 (안전을 위해 패스): {e}")
        return True, "상세페이지 에러 (수동 확인)"

def scrape_jobkorea_target_only():
    """기업 분류별 키워드를 적용하여 잡코리아를 초고속 타격하는 메인 함수"""
    print("🤖 [잡코리아 봇] 국내/외국 분류 매칭 + 초고속 딥 크롤링 가동...")
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    companies_list = load_target_companies()
    if not companies_list:
        return
        
    for item in companies_list:
        company_name = item["name"]
        company_type = item["type"] # '국내' 또는 '외국'
        
        # 기업 분류에 따라 필터링할 제목 키워드 세트를 칼같이 지정합니다.
        if "외국" in company_type:
            title_keywords = GLOBAL_TITLE_KEYWORDS
            type_tag = "외국기업"
        else:
            title_keywords = KR_TITLE_KEYWORDS
            type_tag = "국내기업"
            
        print(f"🎯 타겟 기업 스캔: [{company_name}] ({type_tag})")
        url = f"https://www.jobkorea.co.kr/Search/?stext={company_name}"
        
        try:
            res = requests.get(url, headers=headers, timeout=5)
            soup = BeautifulSoup(res.text, "html.parser")
            job_listings = soup.select(".list-default .list-post") or soup.select("li.list-post")
            
            for listing in job_listings[:5]:  # 기업당 최신 공고 5개 검사
                title_el = listing.select_one(".post-list-info a") or listing.select_one(".title a")
                corp_el = listing.select_one(".corp-name a") or listing.select_one(".name a")
                
                if title_el and corp_el:
                    title = title_el.get_text(strip=True)
                    corp = corp_el.get_text(strip=True)
                    
                    # 1. 철저한 기업명 일치 여부 방어막
                    company_clean = company_name.replace(" ", "").lower()
                    corp_clean = corp.replace(" ", "").lower()
                    if company_clean not in corp_clean and corp_clean not in company_clean:
                        continue 
                    
                    # 2. 🔥 [기획 반영] 국내/외국 분류별 제목 키워드 1차 필터링
                    # 제목에 지정된 직무/스펙 키워드가 단 하나도 없다면 상세 링크를 열지도 않고 바로 패스!
                    if not any(kw.lower() in title.lower() for kw in title_keywords):
                        continue
                        
                    link = title_el["href"]
                    if not link.startswith("http"):
                        link = "https://www.jobkorea.co.kr" + link
                        
                    print(f"  └ ⚡ 제목 필터 통과 (상세 검사 진입): {title}")
                    
                    # 3. 본문 검사 및 이미지 패스 필터링 진입
                    is_pass, reason = deep_crawl_and_filter(link, headers)
                    
                    if is_pass:
                        results.append({
                            "site": "잡코리아",
                            "company": corp,
                            "title": title,
                            "url": link,
                            "info": f"[★타겟기업-{type_tag}] {reason}"
                        })
                        
        except Exception as e:
            print(f"⚠️ {company_name} 검색 중 에러 발생: {e}")

    # 바구니(JSON)에 결과 저장
    output_file = os.path.join(current_dir, "jobkorea_raw.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
        
    print(f"✅ [잡코리아 봇] 스캔 완료! 총 {len(results)}건의 맞춤 공고 수집됨.")

if __name__ == "__main__":
    scrape_jobkorea_target_only()
