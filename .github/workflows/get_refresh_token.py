# -*- coding: utf-8 -*-
"""
get_refresh_token.py
구글 캘린더용 refresh_token 을 '로컬에서 딱 한 번' 발급받는 스크립트.
발급된 토큰을 GitHub Secret(GOOGLE_REFRESH_TOKEN)에 넣으면 이후 자동 실행에 사용된다.

준비:
    pip install google-auth-oauthlib
실행:
    python get_refresh_token.py
"""

from google_auth_oauthlib.flow import InstalledAppFlow

# ↓↓↓ 방금 구글 클라우드에서 받은 값 두 개를 붙여넣으세요 ↓↓↓
CLIENT_ID = "629058077531-78rn23kpk2e4i0bq20kf00i268gap3il.apps.googleusercontent.com"
CLIENT_SECRET = "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"
# ↑↑↑ 여기만 채우면 됩니다 ↑↑↑

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

client_config = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}

flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
# 브라우저가 열립니다 → 로그인 → 권한 허용
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

print("\n" + "=" * 50)
print("REFRESH TOKEN (이 값을 복사하세요):")
print(creds.refresh_token)
print("=" * 50)