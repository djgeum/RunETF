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
    prefilter.save_candidates(rows)        # Gemini로 넘어가기 직전 목록 저장(검토용)
 
    if not rows:
        telegram_send.send_report([])          # '오늘 없음' 안내
        print("제목필터 후 대상 없음 → 종료")
        return
 
    # 3) Gemini 제목 스크리닝 (본문/URL 안 읽음 → 제목만, 429 방지)
    print("\n[AI] Gemini 제목 스크리닝 시작...")
    kept = ai_filter.batch_title_screen(rows)
 
    # 4) 텔레그램 전송 (통과분만, 0건이면 '없음' 메시지)
    sent = telegram_send.send_report(kept, today_str=now[:10])
 
    # 4-2) 구글 캘린더 등록 — 잠시 보류 (본문 미판독 기간 동안 중단)
    #   재개하려면 아래 주석을 해제하세요.
    # if kept:
    #     try:
    #         import calendar_add
    #         calendar_add.add_deadline_events(kept)
    #     except Exception as e:
    #         print(f"[캘린더] 오류(건너뜀): {e}")
 
    # 5) notified 기록 (전송 성공 시 통과분 기록 → 다음날 재발송 방지)
    if kept and sent:
        select_new.append_notified(kept, now_str=now)
        print(f"[기록] notified {len(kept)}건 추가")
 
    print("\n########## 하루 파이프라인 완료 ##########")
 
 
if __name__ == "__main__":
    main()
