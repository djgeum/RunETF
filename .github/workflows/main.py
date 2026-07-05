import os
import sys
import datetime

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    import fetch_api
    import fetch_scraper
    import ai_filter
    import telegram_logger
except ModuleNotFoundError as e:
    print(f"❌ 부품 파일 로드 오류: {e}")
    print("💡 모든 .py 파일이 '.github/workflows' 안에 있는지 확인하세요.")
    sys.exit(1)


def main():
    print(f"⏰ [작업 시작] {datetime.datetime.now()}")

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    gemini_key = os.getenv("GEMINI_API_KEY")

    logger = telegram_logger.TelegramLogger(token=telegram_token, chat_id=chat_id)
    logger.log("🤖 채용 정보 수집을 시작합니다.")

    all_diag = []  # 전체 진단 로그 수집

    try:
        raw_jobs = []

        # 1. 오픈 API 수집
        api_jobs, api_diag = fetch_api.get_jobs()
        raw_jobs.extend(api_jobs)
        all_diag.extend(api_diag)

        # 2. 웹 스크래핑 수집
        web_jobs, web_diag = fetch_scraper.scrape_jobs()
        raw_jobs.extend(web_jobs)
        all_diag.extend(web_diag)

        # 3. 진단 요약을 텔레그램으로 전송 (0건이든 아니든 항상)
        diag_summary = (
            "🔎 [수집 진단 리포트]\n"
            f"• API 수집: {len(api_jobs)}건\n"
            f"• 웹 스크래핑: {len(web_jobs)}건\n"
            f"• 합계: {len(raw_jobs)}건\n"
            "─────────────\n"
            + "\n".join(all_diag)
        )
        print(diag_summary)
        logger.log(diag_summary)

        if not raw_jobs:
            logger.log(
                "📭 오늘 수집된 공고가 0건입니다.\n"
                "위 진단 로그에서 'status', '셀렉터', '차단' 항목을 확인하세요.\n"
                "특히 GitHub Actions(데이터센터 IP)에서만 0건이면 사이트 차단 가능성이 큽니다."
            )
            return

        # 4. AI 필터링
        print("🧠 Gemini AI 필터링 중...")
        filtered_report = ai_filter.filter_and_summarize(raw_jobs, api_key=gemini_key)

        # 5. 최종 리포트 전송
        logger.send_report(filtered_report)
        print("✅ 모든 작업 완료!")

    except Exception as e:
        error_msg = f"💥 실행 중 에러: {str(e)}"
        print(error_msg)
        logger.log(error_msg)
        if all_diag:
            logger.log("🔎 에러 시점까지의 진단 로그:\n" + "\n".join(all_diag))
        sys.exit(1)


if __name__ == "__main__":
    main()
