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
    """피플앤잡 상세 링크 안으로 들어가 본문 텍스트 및 이미지를 분석합니다."""
    try:
        time.sleep(3) # 🚨 IP 차단 방지를 위한 3초 휴식
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 피플앤잡은 iframe 없이 보통 클래스가 'content' 나 'job-description' 인 곳에 본문이 있습니다.
        # 전체 텍스트를 추출합니다.
        text_content = soup.get_text(strip=True)
        
        if len(text_content) > 200:
            if any(kw.lower() in text_content.lower() for kw in TARGET_KEYWORDS):
                return True, "텍스트 매칭 (적합)"
            else:
                return False, "텍스트 매칭 (직무 불일치)"
        else:
            # 텍스트가 부족하면 AI 이미지 판독 가동
            imgs = soup.select("img")
            if imgs:
                for img in imgs:
                    img_src = img.get("src")
                    # 레이아웃용 로고 이미지가 아닌 본문 이미지로 보이는 것만 필터링
                    if img_src and img_src.startswith("http") and "logo" not in img_src.lower():
                        print(f"   -> 🖼️ 텍스트 부족. 피플앤잡 이미지 AI 판독 시작...")
                        is_relevant = check_image_with_ai(img_src, headers)
                        if is_relevant:
                            return True, "AI 판독 결과 (YES - 타겟 직무 포함)"
                        else:
                            return False, "AI 판독 결과 (NO - 직무 불일치)"
                            
        return True, "상세내용 파악 불가 (수동 확인 요망)"
        
    except Exception as e:
        print(f"   -> ⚠️ 상세 크롤링 실패 (스킵): {e}")
        return False, "에러"

def scrape_peoplenjob_target_only():
    """피플앤잡에서 타겟 기업만 정밀 검색하는 메인 함수"""
    print("🤖 [피플앤잡 봇] 스마트 딥 크롤링 업무를 시작합니다...")
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537
