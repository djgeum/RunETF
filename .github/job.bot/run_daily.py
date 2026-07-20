# -*- coding: utf-8 -*-
"""
run_daily.py
전체 파이프라인 지휘자. 매일 아침 이 파일 하나만 실행하면 된다.

순서
  1) 수집 봇 3개 + 매칭 스크립트 3개 실행  (RUN_COLLECTORS=True 일 때)
  2) select_new : 오늘 새로 수집됐고 아직 안 보낸 공고만 추림
  3) ai_filter  : Gemini 로 각 공고 적합성(OK/NO) 판정
  4) telegram_send : OK 공고만 txt 1개로 묶어 텔레그램 전송 (0건이면 '없음' 메시지)
  5) 전송/판정한 공고를 notified 기록에 추가 (다음날 중복 방지)

환경변수(로컬/GitHub Secrets):
    GEMINI_API_KEY, TELEGRAM_BOT_TOKEN(또는 TELEGRAM_TOKEN), TELEGRAM_CHAT_ID

실행:
    python run_daily.py
"""

import sys
import subprocess
from datetime import datetime

# 수집+매칭까지 이 파일에서 실행할지 (False면 select_new 이후 단계만)
RUN_COLLECTORS = True

# 실행 순서 (수집 → 매칭)
COLLECT_STEPS = [
    "jobkorea_bot.py",   "jobkorea_bot_main.py",
    "saramin_bot.py",    "saramin_bot_main.py",
    "peoplenjob_bot.py", "peoplenjob_bot_main.py",
]


def run_script(name):
    """하위 스크립트를 현재 파이썬으로 실행(하나 실패해도 전체는 계속)."""
    print(f"\n===== ▶ {name} =====")
    try:
        subprocess.run([sys.executable, name], check=False)
    except Exception as e:
        print(f"[!] {name} 실행 오류: {e}")


def main():
    import select_new
    import ai_filter
    import telegram_send

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1) 수집 + 매칭
    if RUN_COLLECTORS:
        for step in COLLECT_STEPS:
            run_script(step)

    # 2) 오늘 신규·미알림 추리기
    rows = select_new.get_today_new()
    print(f"\n[신규] 오늘 새로 올라온 미알림 공고: {len(rows)}건")

  # 2-2) 제목 규칙 사전필터 (Gemini 호출 전 대량 축소 → 429 방지)
    import prefilter
    rows = prefilter.filter_rows(rows)

      if not rows:
        telegram_send.send_report([])          # '오늘 없음' 안내
        print("오늘 신규 없음 → 종료")
        return

    # 3) AI 적합성 판정
    print("\n[AI] Gemini 적합성 판정 시작...")
    judged = ai_filter.judge_jobs(rows)
    ok_rows = [r for r in judged if r.get("AI판정") == "OK"]
    no_rows = [r for r in judged if r.get("AI판정") != "OK"]
    print(f"[AI] 판정 결과: OK {len(ok_rows)}건 / NO {len(no_rows)}건")

    # 4) OK 공고만 txt 1개로 전송 (OK 0건이면 '없음' 메시지)
    sent = telegram_send.send_report(ok_rows, today_str=now[:10])

    # 4-2) OK 공고 마감일을 구글 캘린더에 '회사명 마감' 일정으로 등록
    if ok_rows:
        try:
            import calendar_add
            calendar_add.add_deadline_events(ok_rows)
        except Exception as e:
            print(f"[캘린더] 오류(건너뜀): {e}")

    # 5) notified 기록 (NO는 항상 / OK는 전송 성공 시 → 재판정·재전송 방지)
    to_mark = list(no_rows)
    if ok_rows and sent:
        to_mark += ok_rows
    if to_mark:
        select_new.append_notified(to_mark, now_str=now)
        print(f"[기록] notified {len(to_mark)}건 추가")

    print("\n########## 하루 파이프라인 완료 ##########")


if __name__ == "__main__":
    main()
