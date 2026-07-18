import os
import sys
import json
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup

# =====================================================================
# [환경 세팅] 경로 고정 및 피플앤잡(외국계) 전용 매칭 키워드 세팅
# =====================================================================
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# 1차 검문: 피플앤잡 공고 제목에서 거를 외국계 전용 키워드
GLOBAL_TITLE_KEYWORDS = ["마케팅", "신입", "공채", "글로벌", "marketing", "brand", "sales", "intern", "인턴"]

# 2차 검문: 상세 본문 텍스트 내에 포함되어야 할 직무 키워드
JOB_KEYWORDS = ["해외영업", "글로벌", "마케팅", "화장품", "영업", "sales", "global", "marketing"]


def load_foreign_companies():
    """target_companies.xlsx 파일에서 '기업분류'가 '외국'인 기업만 쏙 뽑아옵니다."""
    excel_path = os.path.join(current_dir, "target_companies.xlsx")
    if not os.path.exists(excel_path):
        print("ℹ️ [피플앤잡 봇] target_companies.xlsx 파일이 없어 종료합니다.")
        return []
    try:
        df = pd.read_excel(excel_path)
        if "기업명" in df.columns and "기업분류" in df.columns:
            foreign_companies = []
            for _, row in df.iterrows():
                # 기업분류가 '외국'인 데이터만 안전하게 필터링
                if pd.notna(row["기업명"]) and pd.notna(row["기업분류"]):
                    c_type = str(row["기업분류"]).strip()
                    if "외국" in c_type:
                        foreign_companies.append(str(row["기업명"]).strip())
            print(f"📂 [피플앤잡 봇] 엑셀에서 {len(foreign_companies)}개의 '외국계 타겟 기업'을 찾았습니다.")
            return foreign_companies
        else:
            print("⚠️ [피플앤잡 봇] 엑셀에 '기업명' 또는 '기업분류' 열이 없습니다.")
            return []
    except Exception as e:
        print(f"❌ [피플앤잡 봇] 엑셀 읽기 오류: {e}")
        return []

def deep_crawl_and_filter(url, headers):
    """[초고속 버전] 상세 페이지 본문 텍스트를 읽고, 통이미지면 바로 수동 확인 태그를 달아 토스합니다."""
    try:
        time.sleep(0.5) # IP 차단 방지를 위한 최소한의 안전장치
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 피플앤잡은 iframe 없이 보통 본문 텍스트가 노출되므로 바로 긁어옵니다.
        text_content = soup.get_text(strip=True)
        
        if len(text_content) > 150:
            # 본문 텍스트가 풍부한 일반 공고인 경우 직무 키워드 2차 검사
            if any(kw.lower() in text_content.lower() for kw in JOB_KEYWORDS):
                return True, "본문 텍스트 매칭 성공"
            else:
                return False, "직무 불일치 (본문 내용 무관)"
        else:
            # 글자가 없고 통이미지 팝업 형태인 경우, 무거운 AI 없이 바로 합격 토스!
            return True, "통이미지 공고 (★수동 링크 확인 필요)"
            
    except Exception as e:
        print(f"   -> ⚠️ 상세 크롤링 에러 (안전을 위해 패스): {e}")
        return True, "상세페이지 에러 (수동 확인)"

def scrape_peoplenjob_target_only():
    """오직 외국계 기업만 검색하여 초고속으로 피플앤잡을 타격하는 메인 함수"""
    print("🤖 [피플앤잡 봇] 외국계 기업 전용 타격 + 초고속 딥 크롤링 가동...")
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    foreign_companies = load_foreign_companies()
    if not foreign_companies:
        return
        
    for company in foreign_companies:
        print(f"🎯 외국계 타겟 기업 스캔: [{company}]")
        url = f"https://www.peoplenjob.com/jobs?q={company}"
        
        try:
            res = requests.get(url, headers=headers, timeout=5)
            soup = BeautifulSoup(res.text, "html.parser")
            
            # 피플앤잡 공고 링크 태그들 수집
            job_links = soup.select("a")
            valid_jobs = []
            
            for a_tag in job_links:
                href = a_tag.get("href", "")
                if "/jobs/" in href and not href.endswith("/jobs/"):
                    title = a_tag.get_text(strip=True)
                    
                    # 1. 🔥 [기획 반영] 공고 제목 키워드 1차 필터링
                    # 제목에 지정된 외국계 마케팅/신입 키워드가 없다면 상세 검사를 시작도 안 하고 스킵!
                    if not any(kw.lower() in title.lower() for kw in GLOBAL_TITLE_KEYWORDS):
                        continue
                        
                    if len(title) > 5:
                        link = href if href.startswith("http") else "https://www.peoplenjob.com" + href
                        valid_jobs.append((title, link))
            
            # 중복 제거 후 최신 3개만 깊게 검사
            valid_jobs = list(set(valid_jobs))[:3]
            
            for title, link in valid_jobs:
                print(f"  └ ⚡ 제목 필터 통과 (상세 검사 진입): {title}")
                
                # 2. 본문 검사 및 이미지 패스 필터링 진입
                is_pass, reason = deep_crawl_and_filter(link, headers)
                
                if is_pass:
                    results.append({
                        "site": "피플앤잡",
                        "company": company,
                        "title": title,
                        "url": link,
                        "info": f"[★타겟기업-외국기업] {reason}"
                    })
                        
        except Exception as e:
            print(f"⚠️ {company} 검색 중 에러 발생: {e}")

    # 바구니(JSON)에 결과 저장
    output_file = os.path.join(current_dir, "peoplenjob_raw.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
        
    print(f"✅ [피플앤잡 봇] 스캔 완료! 총 {len(results)}건의 맞춤 외국계 공고 수집됨.")

if __name__ == "__main__":
    scrape_peoplenjob_target_only()
