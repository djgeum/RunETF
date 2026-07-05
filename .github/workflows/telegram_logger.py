import os
import requests

class TelegramLogger:
    def __init__(self, token=None, chat_id=None):
        # 외부에서 주입되지 않았다면 환경 변수(GitHub Secrets)에서 직접 가져옵니다.
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def log(self, message):
        """단순 텍스트 메시지(진행 상황 알림 등)를 텔레그램으로 보냅니다."""
        if not self.token or not self.chat_id:
            print("⚠️ 텔레그램 토큰 또는 Chat ID가 설정되지 않아 메시지를 보낼 수 없습니다.")
            print(f"[로그 출력]: {message}")
            return

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code != 200:
                print(f"❌ 텔레그램 메시지 전송 실패 (상태 코드: {response.status_code})")
        except Exception as e:
            print(f"❌ 텔레그램 전송 중 예외 발생: {e}")

    def send_report(self, report_text, filename="채용_정보_요약_리포트.txt"):
        """최종 AI 분석 결과를 .txt 파일로 만들어서 텔레그램 채널로 배달합니다."""
        if not self.token or not self.chat_id:
            print("⚠️ 텔레그램 토큰 또는 Chat ID가 없어 파일 전송을 취소합니다.")
            return

        # 1. 텍스트 내용을 가상 환경 내에 실제 임시 파일로 저장합니다.
        with open(filename, "w", encoding="utf-8") as f:
            f.write(report_text)

        url = f"{self.base_url}/sendDocument"
        
        # 2. 저장한 파일을 열어 텔레그램으로 쏘아 올립니다.
        try:
            with open(filename, "rb") as document:
                files = {"document": (filename, document)}
                payload = {
                    "chat_id": self.chat_id,
                    "caption": "📋 Gemini AI가 선별한 맞춤형 신규 채용 정보 리포트가 도착했습니다!"
                }
                response = requests.post(url, data=payload, files=files, timeout=20)
                
                if response.status_code == 200:
                    print("🚀 채용 정보 리포트 파일 배달 완료!")
                else:
                    print(f"❌ 리포트 파일 전송 실패 (상태 코드: {response.status_code})")
                    # 파일 전송 실패 시 텍스트로라도 백업 전송 시도
                    self.log("⚠️ 리포트 파일 전송에 실패하여 텍스트로 대체하여 보냅니다.\n\n" + report_text[:3000])
                    
        except Exception as e:
            print(f"❌ 파일 배달 중 예외 발생: {e}")
        finally:
            # 3. 전송이 끝나면 가상 컴퓨터 안의 임시 파일을 깔끔하게 지워줍니다.
            if os.path.exists(filename):
                os.remove(filename)
