import os
import requests

class TelegramLogger:
    def __init__(self, token=None, chat_id=None):
        """
        텔레그램 알림 및 리포트 발송을 담당하는 클래스입니다.
        config.py 또는 GitHub Secrets에서 전달받은 토큰과 ID를 사용합니다.
        """
        self.token = token
        self.chat_id = chat_id

    def log(self, message):
        """간단한 텍스트 메시지를 텔레그램으로 전송합니다."""
        if not self.token or not self.chat_id:
            print(f"⚠️ [Telegram] 토큰 또는 Chat ID가 없어 콘솔에만 출력합니다:\n{message}")
            return
        
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown"  # 이모지와 굵은 글씨가 깔끔하게 나오도록 지원
        }
        try:
            res = requests.post(url, json=payload, timeout=10)
            if res.status_code != 200:
                # 마크다운 문법 오류 등으로 전송 실패 시 일반 텍스트로 재시도
                payload.pop("parse_mode", None)
                requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"❌ 텔레그램 메시지 전송 중 오류 발생: {e}")

    def send_report(self, report_text, filename="채용_리포트.txt"):
        """
        내용이 길어 텔레그램 한 자 제한(4000자)을 넘을 수 있으므로,
        텍스트 파일 파일로 깔끔하게 묶어서 전송합니다.
        """
        if not self.token or not self.chat_id:
            print("⚠️ [Telegram] 토큰 또는 Chat ID가 없어 파일 전송을 건너뜁니다.")
            print(report_text)
            return

        # 1. 먼저 요약 안내 메시지 발송
        today_str = os.getenv("DATE_STR") or "오늘"
        self.log(f"📋 *[{today_str}] 맞춤형 채용 공고 분석 리포트 배달 완료!*\n아래 첨부된 파일을 다운로드하여 확인해 주세요.")

        # 2. 진짜 결과물은 텍스트 파일(.txt) 파일로 쏴주기
        url = f"https://api.telegram.org/bot{self.token}/sendDocument"
        try:
            # 메모리상에서 즉석으로 텍스트 파일화하여 텔레그램 서버에 업로드
            files = {
                "document": (filename, report_text.encode("utf-8"), "text/plain")
            }
            data = {
                "chat_id": self.chat_id
            }
            res = requests.post(url, data=data, files=files, timeout=20)
            if res.status_code == 200:
                print("🚀 텔레그램으로 최종 채용 리포트 파일 전송 성공!")
            else:
                print(f"❌ 텔레그램 파일 전송 실패 (상태코드: {res.status_code}): {res.text}")
                # 파일 실패 시 차선책으로 본문 내용 자체를 텍스트로 강제 전송 시도
                self.log(report_text[:3900] + "\n\n... (내용이 길어 중간 생략)")
        except Exception as e:
            print(f"❌ 텔레그램 파일 전송 중 대형 오류 발생: {e}")
