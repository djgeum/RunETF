import os
import sys
import json
import time
import requests
from bs4 import BeautifulSoup

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# 🔥 [지시 반영] 1, 2차 통합 핵심 직무 키워드
CORE_KEYWORDS = ["마케팅", "해외영업", "신입", "공채", "글로벌", "marketing", "MD", "브랜드"]

def deep_crawl_and_filter(url, headers):
    try:
        time.sleep(0.5)
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")
        text_content = soup.get_text(strip=True)
        if len(text_content) > 150:
            if any(kw.lower() in text_content.lower() for kw in CORE_KEYWORDS):
                return True, "본문 텍스트 매칭 성공"
            else:
                return False, "직무 불일치"
        else:
            return True, "통이미지 공고 (★수동 링크 확인 필요)"
    except Exception as e:
        return True, f"상세페이지 분석 제한 (수동 확인): {e}"

def scrape_peoplenjob_target_only():
    print("🤖 [피플앤잡 봇] 사명 제한 해제 ➔ AI-Jobs 직무 키워드 광역 스캔 시작...")
    results = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

    # 🔥 특정 기업명 매칭을 하지 않고, 직무 키워드로 ai-jobs를 통째로 검색
    for keyword in ["마케팅", "해외영업", "marketing", "sales"]:
        print(f"🎯 피플앤잡 AI 스마트 검색창 입력: [{keyword}]")
        url = f"https://www.peoplenjob.com/ai-jobs?q={keyword}"
        
        try:
            res = requests.get(url, headers=headers, timeout=5)
            soup = BeautifulSoup(res.text, "html.parser")
            job_rows = soup.select(".job-title a") or soup.select("table tr")
            
            for row in job_rows:
                a_tag = row if row.name == 'a' else row.select_one("a")
                if not a_tag: continue
                
                href = a_tag.get("href", "")
                if "/jobs/" in href and not href.endswith("/jobs/"):
                    title = a_tag.get_text(strip=True)
                    
                    # 1차 제목 키워드 검사 (8대 통일 키워드 대조)
                    if not any(kw.lower() in title.lower() for kw in CORE_KEYWORDS):
                        continue
                        
                    # 피플앤잡 구조상 본문 행 안에서 회사명 텍스트 추출 시도
                    row_text = row.get_text(strip=True)
                    company_name = row_text.replace(title, "").strip().split('\n')[0]
                    if not company_name: company_name = "외국계 기업"
                    
                    link = href if href.startswith("http") else "https://www.peoplenjob.com" + href
                    print(f"  └ ⚡ AI-Jobs 조건 일치 공고 발견: {title} ({company_name})")
                    
                    is_pass, reason = deep_crawl_and_filter(link, headers)
                    if is_pass:
                        results.append({
                            "site": "피플앤잡",
                            "company": company_name,
                            "title": title,
                            "url": link,
                            "info": f"[외국계 AI광역매칭] {reason}"
                        })
                            
            except Exception as e:
                print(f"⚠️ 피플앤잡 AI 검색 에러: {e}")
            time.sleep(0.5)

    unique_results = {res["url"]: res for res in results}.values()
    with open(os.path.join(current_dir, "peoplenjob_raw.json"), "w", encoding="utf-8") as f:
        json.dump(list(unique_results), f, ensure_ascii=False, indent=4)
    print(f"✅ [피플앤잡 봇] 완료! 총 {len(unique_results)}건 수집됨.")

if __name__ == "__main__":
    scrape_peoplenjob_target_only()
