"""
main.py
───────
GitHub Actions 진입점 + 로컬 스케줄러

사용법:
  python main.py --now    # 즉시 1회 실행 (GitHub Actions / 테스트)
  python main.py --data   # 데이터 수집만 확인 (발송 없음)
  python main.py          # 로컬 스케줄러 (매일 SEND_TIME 에 자동 실행)
"""

import os
import sys
import json
import time

# GitHub Actions에서는 .env 파일 없음 (Secrets로 주입됨)
# 로컬에서는 .env 파일 사용
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # GitHub Actions 환경에서는 python-dotenv 불필요

from data_collector import collect_all_data
from analyzer import run_analysis_and_send


def job():
    from datetime import datetime
    print(f"\n{'='*50}")
    print(f"⏰ 작업 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")
    try:
        data     = collect_all_data()
        analysis = run_analysis_and_send(data)
        preview  = analysis[:300] + "..." if len(analysis) > 300 else analysis
        print(f"\n📋 분석 미리보기:\n{preview}")
    except Exception as e:
        import traceback
        print(f"❌ 작업 실패: {e}")
        traceback.print_exc()
        sys.exit(1)   # GitHub Actions가 실패로 인식하도록 exit code 1


def run_data_only():
    data    = collect_all_data()
    display = {k: v for k, v in data.items() if k != "earnings_news_prompt"}
    print(json.dumps(display, ensure_ascii=False, indent=2))


def main():
    args = sys.argv[1:]

    if "--data" in args:
        print("📊 데이터 수집 테스트 모드 (발송 없음)")
        run_data_only()
        return

    if "--now" in args:
        print("🚀 즉시 실행 모드")
        job()
        return

    # ── 로컬 스케줄러 모드 ──
    try:
        import schedule
    except ImportError:
        print("❌ 'schedule' 패키지가 없습니다: pip install schedule")
        sys.exit(1)

    send_time = os.environ.get("SEND_TIME", "07:00")
    print(f"⏰ 로컬 스케줄러 시작 → 매일 {send_time} 실행")
    print("   즉시 실행: python main.py --now")
    print("   데이터 확인: python main.py --data")
    print("   중지: Ctrl+C\n")

    schedule.every().day.at(send_time).do(job)
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
