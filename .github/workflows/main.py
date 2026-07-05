import sys
import os

# 📂 현재 main.py 파일이 있는 폴더(.github/workflows) 위치를 찾습니다.
current_dir = os.path.dirname(os.path.abspath(__file__))

# 🎯 파이썬에게 이 폴더 내부를 먼저 뒤져서 fetch_api, fetch_scraper 등을 찾으라고 순위를 1등으로 올려줍니다.
sys.path.insert(0, current_dir)

# ----------------------------------------------------------------------
# (이 아래부터는 기존에 있던 import requests, import fetch_api 등 원래 코드가 그대로 이어지면 됩니다!)

import os
import requests
import datetime
import fetch_api
import fetch_scraper
import ai_filter
import telegram_logger

# 🔐 깃허브 비밀 금고(Secrets)에서 텔레그램 주소들을 가져옵니다.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_txt_file_to_telegram(file_path, caption_text):
    """
    생성된 .txt 파일을 텔레그램으로 전송하는 함수입니다.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ 텔레그램 토큰 또는 채팅 ID가 설정되지 않았습니다.")
        return

    # 텔레그램 파일 전송 API 주소입니다.
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    
    try:
        # 파일을 읽기 모드로 열어서 텔레그램 서버로 보낼 준비를 합니다.
        with open(file_path, "rb") as file_to_send:
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption_text, # 파일 밑에 붙을 설명 글
                "parse_mode": "HTML"
            }
            files = {
                "document": file_to_send
            }
            response = requests.post(url, data=payload, files=files, timeout=20)
            
            if response.status_code == 200:
                print("✅ 텔레그램으로 .txt 보고서 파일 전송 성공!")
            else:
                print(f"❌ 텔레grams 파일 전송 실패 (코드: {response.status_code})")
    except Exception as e:
        telegram_logger.log_error("main.py (텔레그램 파일 전송 중)", e)


def main():
    print("🏁 [시스템] 채용공고 자동화 비서 시스템을 시작합니다.")
    
    # 오늘 날짜 이쁘게 뽑기 (예: 2026-07-05)
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    # 1단계: API 기반 사이트(사람인, 고용24)에서 수집
    api_jobs = fetch_api.run_api_collection()
    
    # 2단계: 크롤링 기반 사이트(잡코리아, 피플앤잡)에서 수집
    scraped_jobs = fetch_scraper.run_scraper_collection()
    
    # 3단계: 가져온 모든 공고를 하나의 바구니로 합치기
    all_collected_jobs = api_jobs + scraped_jobs
    print(f"📦 [총합] 오늘 수집된 전체 공고 개수: {len(all_collected_jobs)}개")
    
    # 4단계: Gemini AI에게 분석 요청해서 최종 리포트(글) 받기
    report_content = ai_filter.run_ai_filter(all_collected_jobs)
    
    # 5단계: ★질문자님 요청★ 리포트를 .txt 파일로 저장하기
    filename = f"채용_추천_보고서_{today_str}.txt"
    
    try:
        # 가상 컴퓨터 메모리에만 존재하는 글자를 진짜 .txt 파일로 만듭니다.
        # 인코딩을 utf-8로 해야 한글이 깨지지 않고 메모장에서 잘 열립니다!
        with open(filename, "w", encoding="utf-8") as f:
            f.write(report_content)
        print(f"💾 [파일 저장] {filename} 생성이 완료되었습니다.")
        
        # 6단계: 완성된 텍스트 파일을 텔레그램으로 전송!
        caption = f"📅 <b>{today_str} 아침 AI 채용 분석 리포트</b>\n요청하신 .txt 파일이 도착했습니다. 다운로드하여 확인하세요!"
        send_txt_file_to_telegram(filename, caption)
        
    except Exception as e:
        telegram_logger.log_error("main.py (TXT 파일 생성 및 총괄 과정 중)", e)

    print("🏁 [시스템] 모든 작업이 안전하게 종료되었습니다.")


if __name__ == "__main__":
    main()
