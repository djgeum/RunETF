import os
import sys
import json
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
from io import BytesIO
from PIL import Image
import google.generativeai as genai

# =====================================================================
# [환경 세팅] 경로 및 AI 모델 초기화
# =====================================================================
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

API_KEY = os.getenv("GEMINI_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)
ai_model = genai.GenerativeModel('gemini-1.5-flash')

# 질문자님의 타겟 핵심 직무 키워드
TARGET_KEYWORDS = ["해외영업", "글로벌", "마케팅", "화장품", "영업", "sales", "global", "marketing"]


def load_target_companies():
    """엑셀 파일에서 타겟 기업 리스트를 가져옵니다."""
    excel_path = os.path.join(current_dir, "target_companies.xlsx")
    if not os.path.exists(excel_path):
        print("ℹ️ target_companies.xlsx 파일이 없어 종료합니다.")
        return []
    try:
        df = pd.read_excel(excel_path)
        if "기업명" in df.columns:
            return df["기업명"].dropna().astype(str).str.strip().tolist()
    except Exception as e:
        print(f"❌ 엑셀 읽기 오류: {e}")
    return []

def check_image_with_ai(image_url, headers):
    """(AI 시각 기능) 이미지를 다운로드하여 직무 관련성이 있는지 묻습니다."""
    if not API_KEY:
        return True
    
    try:
        res = requests.get(image_url, headers=headers, timeout=10)
        img = Image.open(BytesIO(res.content))
        
        prompt = "이 채용 공고 이미지 안에 '해외영업', '마케팅', '글로벌', '화장품' 직무와 관련된 채용 내용이 포함되어 있나요? 관련된 직무가 하나라도 있다면 'YES', 완전히 무관한 직무(예: 재무, 생산직, IT개발 등)만 있다면 'NO'로만 짧게 대답하세요."
        
        response = ai_model.generate_content([prompt, img])
        result_text = response.text.strip().upper()
        
        return "YES" in result_text
    except Exception as e:
        print(f"      ⚠️ 이미지 AI 판독 중 에러 (안전을 위해 수집 유지): {e}")
        return True

def deep_crawl_and_filter(url, headers):
    """잡코리아 상세 링크 안으로 들어가 본문 텍스트 및 이미지를 분석합니다."""
    try:
        time.sleep(3) # 🚨 IP 차단 방지를 위한 3초 휴식
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 잡코리아는 주로 gib_frame 이라는 이름의 iframe에 상세 내용을 숨깁니다.
        iframe = soup.select_one("iframe#gib_frame")
        if iframe and iframe.has_attr("src"):
            iframe_src = iframe["src"]
            if not iframe_src.startswith("http"):
                iframe_src = "https://www.jobkorea.co.kr" + iframe_src
                
            time.sleep(1)
            iframe_res = requests.get(iframe_src, headers=headers, timeout=10)
            iframe_soup = BeautifulSoup(iframe_res.text, "html.parser")
            
            # 1. 텍스트 추출 검사
            text_content = iframe_soup.get_text(strip=True)
            
            if len(text_content) > 200:
                if any(kw.lower() in text_content.lower() for kw in TARGET_KEYWORDS):
                    return True, "텍스트 매칭 (적합)"
                else:
                    return False, "텍스트 매칭 (직무 불일치)"
            else:
                # 2. 텍스트가 부족하면 AI 이미지 판독 가동
                imgs = iframe_soup.select("img")
                if imgs:
                    for img in imgs:
                        img_src = img.get("src")
                        if img_src and img_src.startswith("http"):
                            print(f"   -> 🖼️ 텍스트 부족. 잡코리아 이미지 AI 판독 시작...")
                            is_relevant = check_image_with_ai(img_src, headers)
                            if is_relevant:
                                return True, "AI 판독 결과 (YES - 타겟 직무 포함)"
                            else:
                                return False, "AI 판독 결과 (NO - 직무 불일치)"
                                
        return True, "상세내용 파악 불가 (수동 확인 요망)"
        
    except Exception as e:
        print(f"   -> ⚠️ 상세 크롤링 실패 (스킵): {e}")
        return False, "에러"

def scrape_jobkorea_target_only():
    """잡코리아에서 타겟 기업만 정밀 검색하는 메인 함수"""
    print("🤖 [잡코리아 봇] 스마트 딥 크롤링 업무를 시작합니다...")
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    target_companies = load_target_companies()
    if not target_companies:
        return
        
    for company in target_companies:
        print(f"\n🎯 타겟 기업 검색 중: [{company}]")
        # 잡코리아 통합 검색 URL
        url = f"https://www.jobkorea.co.kr/Search/?stext={company}"
        time.sleep(2)
        
        try:
            res = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, "html.parser")
            
            # 잡코리아 일반 공고 리스트 추출
            job_listings = soup.select(".list-default .list-post") or soup.select("li.list-post")
            
            for item in job_listings[:3]: # 과도한 접속 방지 (최대 3개)
                title_el = item.select_one(".post-list-info a") or item.select_one(".title a")
                corp_el = item.select_one(".corp-name a") or item.select_one(".name a")
                
                if title_el and corp_el:
                    title = title_el.get_text(strip=True)
                    corp = corp_el.get_text(strip=True)
                    
                    link = title_el["href"]
                    if not link.startswith("http"):
                        link = "https://www.jobkorea.co.kr" + link
                    
                    print(f" └ 발견된 공고: {title}")
                    
                    # 🚀 상세 페이지 딥 크롤링 진입
                    is_pass, reason = deep_crawl_and_filter(link, headers)
                    
                    if is_pass:
                        print(f"    ✅ 수집 통과: {reason}")
                        results.append({
                            "site": "잡코리아",
                            "company": corp,
                            "title": title,
                            "url": link,
                            "info": f"[★타겟기업] {reason}"
                        })
                    else:
                        print(f"    🗑️ 수집 거절: {reason}")
                        
        except Exception as e:
            print(f"⚠️ {company} 검색 중 에러 발생: {e}")

    # 최종 결과물 바구니(JSON)에 따로 저장
    output_file = os.path.join(current_dir, "jobkorea_raw.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
        
    print(f"\n✅ [잡코리아 봇] 딥 크롤링 완료! 총 {len(results)}건의 '진짜' 공고가 수집되었습니다.")

if __name__ == "__main__":
    scrape_jobkorea_target_only()
