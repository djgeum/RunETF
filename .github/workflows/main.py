import os
import sys
import datetime

# =====================================================================
# [핵심] 폴더 경로 고정 시스템
# 모든 파일이 .github/workflows 안에 모여있으므로, 
# 현재 main.py가 실행되는 위치를 파이썬의 탐색 1순위 경로로 강제 지정합니다.
# =====================================================================
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# 이제 같은 폴더(.github/workflows)에 있는 부품들을 에러 없이 깨끗하게 불러옵니다.
try:
    import fetch_api
    import fetch_scraper
    import ai_filter
    import telegram_logger
except ModuleNotFoundError as e:
    print(f"❌ 부품 파일을 불러오는 중 오류 발생: {e}")
    print("💡 모든 파이썬 파일들(.py)이 '.github/workflows' 폴더 안에 모여있는지 다시 확인해 주세요!")
    sys.exit(1)


def main():
    print(f"⏰ [작업 시작] 채용 정보 수집 및 AI 필터링 로봇 가동 - {datetime.datetime.now()}")
    
    # 1. 환경 변수(깃허브 Secrets 기입 내용) 확인 및 준비
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    gemini_key = os.getenv("GEMINI_API_KEY")
    
    # 텔레그램 로거 초기화
    logger = telegram_logger.TelegramLogger(token=telegram_token, chat_id=chat_id)
    logger.log("🤖 채용 정보 인공지능 비서가 수집 작업을 시작합니다.")

    try:
        # 2. 채용 데이터 수집 (API 및 스크래핑 엔진 가동)
        print("🔍 채용 사이트에서 신규 공고를 탐색하는 중...")
        raw_jobs = []
        
        # 사람인/고용노동부 API 등에서 데이터 수집
        raw_jobs.extend(fetch_api.get_jobs())
        # 상세 웹 스크래핑 데이터 수집
        raw_jobs.extend(fetch_scraper.scrape_jobs())
        
        print(f"📋 총 {len(raw_jobs)}건의 구직 공고를 발견했습니다.")
        
        if not raw_jobs:
            logger.log("📭 오늘은 새로 업데이트된 채용 공고가 없습니다.")
            return

        # 3. AI 필터링 및 요약 (Gemini AI 엔진 가동)
        print("🧠 Gemini AI를 이용하여 맞춤형 공고 필터링 진행 중...")
        filtered_report = ai_filter.filter_and_summarize(raw_jobs, api_key=gemini_key)
        
        # 4. 최종 결과 리포트를 텔레그램 채널로 배달
        print("🚀 분석 완료! 텔레그램 채널로 보고서 전송 중...")
        logger.send_report(filtered_report)
        
        print("✅ 모든 채용 정보 배달 작업이 대성공으로 끝났습니다!")
        
    except Exception as e:
        error_msg = f"💥 프로그램 실행 중 예기치 못한 에러가 발생했습니다: {str(e)}"
        print(error_msg)
        logger.log(error_msg)
        sys.exit(1)

if __name__ == "__main__":
    main()
