import os
import requests

try:
    import config
    DEFAULT_FILENAME = getattr(config, "DEFAULT_REPORT_FILENAME", "채용_정보_요약_리포트.txt")
except ImportError:
    DEFAULT_FILENAME = "채용_정보_요약_리포트.txt"


class TelegramLogger:
    def __init__(self, token=None, chat_id=None):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def log(self, message):
        """단순 텍스트 메시지 전송. (Markdown 파싱 미사용 → 특수문자 안전)"""
        if not self.token or not self.chat_id:
            print("⚠️ 텔레그램 토큰/Chat ID 없음. 로그만 출력.")
            print(f"[로그]: {message}")
            return

        url = f"{self.base_url}/sendMessage"
        # 텔레그램 텍스트 상한(4096자) 방어
        text = message if len(message) <= 4000 else message[:4000] + "\n...(생략)"
        payload = {"chat_id": self.chat_id, "text": text}  # parse_mode 제거

        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code != 200:
                print(f"❌ 텔레그램 전송 실패 status={response.status_code}, body={response.text[:200]}")
        except Exception as e:
            print(f"❌ 텔레그램 전송 예외: {e}")

    def send_report(self, report_text, filename=None):
        """AI 리포트를 .txt 파일로 만들어 전송."""
        filename = filename or DEFAULT_FILENAME
        if not self.token or not self.chat_id:
            print("⚠️ 텔레그램 정보 없음 → 파일 전송 취소.")
            return

        with open(filename, "w", encoding="utf-8") as f:
            f.write(report_text)

        url = f"{self.base_url}/sendDocument"
        try:
            with open(filename, "rb") as document:
                files = {"document": (filename, document)}
                payload = {
                    "chat_id": self.chat_id,
                    "caption": "📋 AI가 선별한 맞춤형 채용 리포트가 도착했습니다!",
                }
                response = requests.post(url, data=payload, files=files, timeout=20)
                if response.status_code == 200:
                    print("🚀 리포트 파일 배달 완료!")
                else:
                    print(f"❌ 파일 전송 실패 status={response.status_code}, body={response.text[:200]}")
                    self.log("⚠️ 파일 전송 실패 → 텍스트로 대체 전송.\n\n" + report_text[:3500])
        except Exception as e:
            print(f"❌ 파일 배달 예외: {e}")
            self.log("⚠️ 파일 배달 예외 → 텍스트로 대체 전송.\n\n" + report_text[:3500])
        finally:
            if os.path.exists(filename):
                os.remove(filename)
