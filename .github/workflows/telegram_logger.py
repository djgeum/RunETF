import os
import requests
import traceback

# 🔐 깃허브 비밀 금고(Secrets)에 저장해둔 텔레그램 열쇠들을 꺼내옵니다.
# 로봇이 켜지면 깃허브가 자동으로 이 환경 변수들을 가상 컴퓨터에 넣어줍니다.
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_to_telegram(message):
    """
    텔레그램 채널로 일반 문자 메시지를 보내는 단순 배달 함수입니다.
    """
    # 만약 비밀번호 설정이 제대로 안 되어 있다면 실행하지 않고 넘어가요.
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ [경고] 텔레그램 토큰이나 채널 ID가 설정되지 않았습니다.")
        return False

    # 텔레그램 종업원에게 메시지를 배달해달라고 요청할 인터넷 주소예요.
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    # 배달할 내용물 주머니
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"  # 메시지에 글씨 두껍게(<b>) 같은 효과를 주기 위한 옵션이에요!
    }

    try:
        # 실제로 인터넷을 통해 텔레그램 서버로 슝 보냅니다.
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"❌ 텔레그램 메시지 전송 중 통신 실패: {e}")
        return False


def log_error(file_name, error_instance):
    """
    🚨 코드가 고장 났을 때 호출하는 긴급 SOS 함수입니다.
    어떤 파일에서, 무슨 에러가 났는지 상세히 정리해서 텔레그램으로 보내줍니다.
    """
    # traceback 도구를 쓰면 몇 번째 줄에서 왜 에러가 났는지 컴퓨터 대본을 통째로 긁어올 수 있어요.
    error_detail = traceback.format_exc()
    
    # 텔레그램 채널에 알림이 울릴 때 보기 좋게 정장 서식으로 가다듬습니다.
    error_message = (
        f"🚨 <b>[채용 비서 로봇 고장 알림]</b>\n\n"
        f"📂 <b>문제가 발생한 파일:</b> <code>{file_name}</code>\n"
        f"⚠️ <b>에러 종류:</b> {error_instance}\n\n"
        f"🔍 <b>상세 고장 원인 (컴퓨터 로그):</b>\n"
        f"<pre>{error_detail}</pre>\n"
        f"💡 <i>주인님, 가상 컴퓨터가 일하다가 멈췄어요! 깃허브 Actions 로그를 확인해보세요.</i>"
    )
    
    # 다듬어진 메시지를 텔레그램으로 발송합니다.
    send_to_telegram(error_message)
    print(f"🚨 {file_name}에서 에러가 발생하여 텔레그램으로 SOS를 쳤습니다.")
