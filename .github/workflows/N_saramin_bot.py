import os
import sys
import json
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

SEARCH_SUFFIXES = ["마케팅", "해외영업", "MD", "브랜드", "글로벌"]
KR_TITLE_KEYWORDS = ["마케팅", "해외영업", "신입", "공채", "글로벌", "marketing", "md", "브랜드"]
GLOBAL_TITLE_KEYWORDS = ["마케팅", "신입", "공채", "글로벌", "marketing", "brand"]
JOB_KEYWORDS = ["해외영업", "글로벌", "마케팅", "영업", "sales", "global", "marketing"]

def load_target_companies():
    excel_path = os.path.join(current_dir, "target_companies.xlsx")
    if not os.path.exists(excel_path): return []
    try:
        df = pd.read_excel(excel_path)
        if "기업명" in df.columns and "기업분류" in df.columns:
            return [{"name": str(row["기업명"]).strip(), "type": str(row["기업분류"]).strip()} for _, row in df.iterrows() if pd.notna(row["기업명"]) and pd.notna(row["기업분류"])]
    except Exception: pass
    return []

def deep_crawl_and_filter(url, headers):
    try:
        time.sleep(0.5)
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")
        iframe = soup.select_one("iframe#iframe_content_0") or soup.select_one("iframe")
        if iframe and iframe.has_attr("src"):
            iframe_src = iframe["src"]
            if not iframe_src.startswith("http"): iframe_src = "https://www.saramin.co.kr" + iframe_src
            iframe_res = requests.get(iframe_src, headers=headers, timeout=5)
            iframe_soup = BeautifulSoup(iframe_res.text, "html.parser")
            text_content = iframe_soup.get_text(strip=True)
            if len(text_content) > 150:
                if any(kw.lower() in text_content.lower() for kw in JOB_KEYWORDS): return True, "본문 텍스트 매칭 성공"
                else: return False, "직무 불일치"
            else: return True, "통이미지 공고 (★수동 링크 확인 필요)"
        return True, "특수 대기업/외국계 채용 양식 (★수동 링크 확인 필요)"
    except Exception as e:
        return True, f"상세페이지 분석 제한 (수동 확인): {e}"

def scrape_saramin_target_only():
    print("🤖 [사람인 봇] 유료광고 우회 + 회사명+직무 조합 검색 엔진 가동...")
    results = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    companies_list = load_target_companies()
    if not companies_list: return
        
    for item in companies_list:
        company_name = item["name"]
        company_type = item["type"]
        title_keywords = GLOBAL_TITLE_KEYWORDS if "외국" in company_type else KR_TITLE_KEYWORDS
        type_tag = "외국기업" if "외국" in company_type else "국내기업"
        
        for suffix in SEARCH_SUFFIXES:
            combined_keyword = f"{company_name} {suffix}"
            print(f"🎯 사람인 정밀 검색: [{combined_keyword}]")
            url = f"https://www.saramin.co.kr/zf_user/search/recruit?searchword={combined_keyword}"
            
            try:
                res = requests.get(url, headers=headers, timeout=5)
                soup = BeautifulSoup(res.text, "html.parser")
                
                # 🔥 [핵심 방어막] 상단 유료 광고(Premium 등) 영역을 완전히 제외하고, 
                # 오직 일반 검색 결과 리스트 탭(#recruit_info_list) 안의 공고들만 정확히 도려냅니다.
                job_listings = soup.select("#recruit_info_list .item_recruit")
                
                for listing in job_listings[:5]: # 광고가 빠진 순수 리스트이므로 상단 5개면 충분히 커버됨
                    title_el = listing.select_one(".job_tit a")
                    corp_el = listing.select_one(".corp_name a")
                    
                    if title_el and corp_el:
                        title = title_el.get_text(strip=True)
                        corp = corp_el.get_text(strip=True)
                        
                        company_clean = company_name.replace(" ", "").lower()
                        corp_clean = corp.replace(" ", "").lower()
                        if company_clean not in corp_clean and corp_clean not in company_clean: continue 
                        if not any(kw.lower() in title.lower() for kw in title_keywords): continue
                            
                        link = "https://www.saramin.co.kr" + title_el["href"]
                        is_pass, reason = deep_crawl_and_filter(link, headers)
                        if is_pass:
                            results.append({"site": "사람인", "company": corp, "title": title, "url": link, "info": f"[★타겟기업-{type_tag}] {reason}"})
            except Exception as e:
                print(f"⚠️ {combined_keyword} 검색 에러: {e}")
            time.sleep(0.3)

    unique_results = {res["url"]: res for res in results}.values()
    with open(os.path.join(current_dir, "saramin_raw.json"), "w", encoding="utf-8") as f:
        json.dump(list(unique_results), f, ensure_ascii=False, indent=4)
    print(f"✅ [사람인 봇] 완료! 총 {len(unique_results)}건 수집.")

if __name__ == "__main__":
    scrape_saramin_target_only()
