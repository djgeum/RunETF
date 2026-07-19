# -*- coding: utf-8 -*-
"""
calendar_add.py
OK 판정된 공고의 마감일을 구글 캘린더에 '회사명 마감' 종일 일정으로 등록한다.

- 마감일이 실제 날짜로 해석되는 것만 등록. (상시/채용시/미확인 등은 건너뜀)
- run_daily 가 OK 공고 리스트를 넘겨 호출.

인증: OAuth 리프레시 토큰 방식 (환경변수 / GitHub Secrets)
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN

필요 라이브러리:
    pip install google-api-python-client google-auth
"""

import os
import re
from datetime import date, timedelta

CALENDAR_ID = "primary"                    # 내 기본 캘린더. 다른 캘린더면 그 ID로.
TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

# 마감일을 뽑을 컬럼 (AI가 뽑은 값 우선, 없으면 수집 시 마감일)
COL_DEADLINE_AI = "서류마감일_AI"
COL_DEADLINE = "마감일"
COL_COMPANY = "기업명"
COL_TITLE = "공고제목"
COL_URL = "공고링크"

# 날짜가 아닌 마감 표기(등록 건너뜀)
_SKIP_WORDS = ("상시", "채용시", "수시", "충원", "미확인", "미정")


# ===========================================================================
# 마감일 파싱
# ===========================================================================
def parse_deadline(text, today=None):
    """다양한 마감 표기 -> date. 날짜 없으면 None."""
    today = today or date.today()
    if not text:
        return None
    t = str(text).strip()
    if any(w in t for w in _SKIP_WORDS):
        return None
    # YYYY-MM-DD
    m = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    if "오늘마감" in t:
        return today
    if "내일마감" in t:
        return today + timedelta(days=1)
    # D-7
    m = re.search(r"D-(\d+)", t)
    if m:
        return today + timedelta(days=int(m.group(1)))
    # MM/DD (앞에 ~ 나 뒤에 (요일) 붙어도 됨)
    m = re.search(r"(\d{1,2})/(\d{1,2})", t)
    if m:
        mm, dd = int(m.group(1)), int(m.group(2))
        try:
            d = date(today.year, mm, dd)
        except ValueError:
            return None
        if d < today - timedelta(days=1):      # 이미 많이 지났으면 내년으로
            try:
                d = date(today.year + 1, mm, dd)
            except ValueError:
                return None
        return d
    return None


# ===========================================================================
# 구글 캘린더 서비스
# ===========================================================================
def get_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    cid = os.getenv("GOOGLE_CLIENT_ID")
    csecret = os.getenv("GOOGLE_CLIENT_SECRET")
    rtoken = os.getenv("GOOGLE_REFRESH_TOKEN")
    if not (cid and csecret and rtoken):
        raise SystemExit("[오류] GOOGLE_CLIENT_ID/SECRET/REFRESH_TOKEN 환경변수가 없습니다.")

    creds = Credentials(
        token=None,
        refresh_token=rtoken,
        token_uri=TOKEN_URI,
        client_id=cid,
        client_secret=csecret,
        scopes=SCOPES,
    )
    creds.refresh(Request())                   # 액세스 토큰 발급
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


# ===========================================================================
# 일정 등록
# ===========================================================================
def add_deadline_events(rows, calendar_id=CALENDAR_ID):
    """OK 공고 리스트 -> 마감일 있는 것만 '회사명 마감' 종일 일정 등록."""
    if not rows:
        return 0
    service = get_service()
    today = date.today()
    added, skipped = 0, 0
    for r in rows:
        dl_text = r.get(COL_DEADLINE_AI) or r.get(COL_DEADLINE) or ""
        d = parse_deadline(dl_text, today)
        if not d:
            skipped += 1
            continue
        company = r.get(COL_COMPANY, "").strip() or "회사"
        event = {
            "summary": f"{company} 마감",
            "description": f"{r.get(COL_TITLE, '')}\n{r.get(COL_URL, '')}",
            "start": {"date": d.isoformat()},
            "end": {"date": (d + timedelta(days=1)).isoformat()},   # 종일 일정(끝날짜 배타적)
        }
        try:
            service.events().insert(calendarId=calendar_id, body=event).execute()
            added += 1
            print(f"  [캘린더] {company} 마감 → {d.isoformat()}")
        except Exception as e:
            print(f"  [캘린더] 등록 실패 ({company}): {e}")
    print(f"[캘린더] 등록 {added}건 / 마감일없어 건너뜀 {skipped}건")
    return added


# ===========================================================================
# 단독 테스트 (실제 등록됨 - 주의)
# ===========================================================================
if __name__ == "__main__":
    sample = [
        {COL_COMPANY: "테스트기업", COL_TITLE: "글로벌 마케팅",
         COL_DEADLINE_AI: "2026-08-15", COL_URL: "https://example.com/1"},
    ]
    add_deadline_events(sample)
