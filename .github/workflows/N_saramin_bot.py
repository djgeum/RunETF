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

# 🔥 [지시 반영] 통합 핵심 키워드 및 조합용 서픽스
CORE_KEYWORDS = ["마케팅", "해외영업", "신입", "공채", "글로벌", "marketing", "MD", "브랜드"]
SEARCH_SUFFIXES = ["마케팅", "해외영업", "MD", "브랜드", "글로벌"]

def load_target_companies():
    excel_path = os.path.join(current_dir, "target_companies.xlsx")
    if not os.path.exists(excel_path): return []
    try:
        df = pd.read_excel(excel_path)
        if "기업명" in df.columns:
            return [str(name).strip() for name in df["기업명"].dropna()]
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
                if any(kw.lower() in text_content.lower() for kw in CORE_KEYWORDS): return True, "본문 텍스트 매칭 성공"
                else: return False, "직무 불일치"
            else: return True, "통이미지 공고 (★수동 링크 확인 필요)"
        return True, "특수 채용 양식 (★수동 링크 확인 필요)"
    except Exception as e:
        return True, f"상세페이지 분석 제한: {e}"

def scrape_saramin_target_only():
    print("🤖 [사람인 봇] 8대 통일 키워드 + 유료광고 우회 검색 시작...")
    results = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    companies = load_target_companies()
    
    for company_name in companies:
        for suffix in SEARCH_SUFFIXES:
            combined_keyword = f"{company_name} {suffix}"
            print(f"🎯 사람인 조합 정밀 검색: [{combined_keyword}]")
            url = f"https://www.saramin.co.kr/zf_user/search/recruit?searchword={combined_keyword}"
            
            try:
                res = requests.get(url, headers=headers, timeout=5)
                soup = BeautifulSoup(res.text, "html.parser")
                job_listings = soup.select("#recruit_info_list .item_recruit")
                
                for listing in job_listings[:5]:
                    title_el = listing.select_one(".job_tit a")
                    corp_el = listing.select_one(".corp_name a")
                    
                    if title_el and corp_el:
                        title = title_el.get_text(strip=True)
                        corp = corp_el.get_text(strip=True)
                        
                        company_clean = company_name.replace(" ", "").lower()
                        corp_clean = corp.replace(" ", "").lower()
                        if company_clean not in corp_clean and corp_clean not in company_clean: continue 
                        if not any(kw.lower() in title.lower() for kw in CORE_KEYWORDS): continue
                            
                        link = "https://www.saramin.co.kr" + title_el["href"]
                        is_pass, reason = deep_crawl_and_filter(link, headers)
                        if is_pass:
                            results.append({"site": "사람인", "company": corp, "title": title, "url": link, "info": f"[타겟기업] {reason}"})
            except Exception as e:
                print(f"⚠️ {combined_keyword} 검색 에러: {e}")
            time.sleep(0.3)

    unique_results = {res["url"]: res for res in results}.values()
    with open(os.path.join(current_dir, "saramin_raw.json"), "w", encoding="utf-8") as f:
        json.dump(list(unique_results), f, ensure_ascii=False, indent=4)
    print(f"✅ [사람인 봇] 완료! 총 {len(unique_results)}건 수집.")

if __name__ == "__main__":
    scrape_saramin_target_only()
