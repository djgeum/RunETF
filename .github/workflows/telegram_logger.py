import os
import requests

class TelegramLogger:
    def __init__(self, token=None, chat_id=None):
        # 1. 중복된 환경변수 호출 제거, 깔끔한 1:1 매칭
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def log(self, message):
        """단순 텍스트/시스템 진단 로그 메시지 전송"""
        if not self.token or not self.chat_id:
            print("⚠️ 텔레그램 토큰/Chat ID 없음. 로그만 출력.")
            print(f"[로그]: {message}")
            return

        url = f"{self.base_url}/sendMessage"
        # 텔레그램 텍스트 상한(4096자) 방어
        text = message if len(message) <= 4000 else message[:4000] + "\n...(생략)"
        payload = {"chat_id": self.chat_id, "text": text} 

        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code != 200:
                print(f"❌ 텔레그램 로그 전송 실패 status={response.status_code}, body={response.text[:200]}")
        except Exception as e:
            print(f"❌ 텔레그램 로그 전송 예외: {e}")

    def send_report(self, report_text):
        """
        AI 리포트를 파일이 아닌 '채팅 메시지'로 바로 전송하여 
        모바일에서 즉시 읽을 수 있도록 사용자 경험(UX) 극대화.
        """
        if not self.token or not self.chat_id:
            print("⚠️ 텔레그램 정보 없음 → 리포트 전송 취소.")
            print(report_text)
            return

        url = f"{self.base_url}/sendMessage"
        
        # 3~5개 공고 추천은 보통 1500~2000자 내외지만, 
        # 혹시 4000자가 넘을 경우를 대비해 텍스트를 쪼개서(chunk) 순차 전송합니다.
        chunks = [report_text[i:i+4000] for i in range(0, len(report_text), 4000)]
        
        for i, chunk in enumerate(chunks):
            payload = {
                "chat_id": self.chat_id,
                "text": chunk
                # 텔레그램 파싱 에러 방지를 위해 parse_mode는 생략 (이모지는 텍스트 상태로도 잘 출력됨)
            }
            try:
                response = requests.post(url, json=payload, timeout=15)
                if response.status_code == 200:
                    print(f"🚀 AI 추천 리포트 메시지 배달 완료! ({i+1}/{len(chunks)})")
                else:
                    print(f"❌ 리포트 메시지 전송 실패 status={response.status_code}, body={response.text[:200]}")
            except Exception as e:
                print(f"❌ 리포트 메시지 배달 예외: {e}")
