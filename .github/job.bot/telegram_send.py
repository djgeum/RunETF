# -*- coding: utf-8 -*-
"""
telegram_send.py
AI가 OK 판정한 오늘의 공고를 'txt 파일 1개'로 만들어 텔레그램에 전송한다.
(개별 메시지로 여러 번 보내지 않고, 하루치를 파일 한 개로 첨부)

제공 함수 (run_daily 가 사용)
  - build_report_txt(rows, path) : OK 공고 리스트 -> 정리된 txt 파일 생성
  - send_document(path, caption)  : txt 파일을 텔레그램에 문서로 전송
  - send_message(text)            : 짧은 텍스트 알림(예: "오늘 추천 없음")

필요 라이브러리:
    pip install requests
환경변수 (GitHub Secrets):
    TELEGRAM_BOT_TOKEN  (없으면 TELEGRAM_TOKEN)
    TELEGRAM_CHAT_ID

단독 테스트:
    python telegram_send.py          # 연결 테스트 메시지 1건 전송
"""

import os
from datetime import date

import requests

# ===========================================================================
# 설정 / 자격증명 (환경변수)
# ===========================================================================
def _token():
    tok = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    if not tok:
        raise SystemExit("[오류] TELEGRAM_BOT_TOKEN(또는 TELEGRAM_TOKEN) 환경변수가 없습니다.")
    return tok


def _chat_id():
    cid = os.getenv("TELEGRAM_CHAT_ID")
    if not cid:
        raise SystemExit("[오류] TELEGRAM_CHAT_ID 환경변수가 없습니다.")
    return cid


def _api(method):
    return f"https://api.telegram.org/bot{_token()}/{method}"


# 리포트에 쓸 컬럼(있으면 사용)
COL_SOURCE = "출처"
COL_COMPANY = "기업명"
COL_TITLE = "공고제목"
COL_URL = "공고링크"
COL_DEADLINE_AI = "서류마감일_AI"      # ai_filter 가 붙인 마감일
COL_DEADLINE = "마감일"                 # 수집 시 마감일(폴백)
COL_REASON = "판정이유"


# ===========================================================================
# 리포트 txt 생성
# ===========================================================================
def build_report_txt(rows, path=None, today_str=None):
    """OK 공고 리스트 -> 사람이 읽기 좋은 txt 파일 생성. 파일 경로 반환."""
    today_str = today_str or date.today().isoformat()
    path = path or f"추천공고_{today_str}.txt"

    lines = [f"[오늘의 추천 채용공고] {today_str}  (총 {len(rows)}건)", "=" * 40, ""]
    for i, r in enumerate(rows, 1):
        deadline = r.get(COL_DEADLINE_AI) or r.get(COL_DEADLINE) or "미확인"
        lines.append(f"{i}. ({r.get(COL_SOURCE,'')}) {r.get(COL_COMPANY,'')} — {r.get(COL_TITLE,'')}")
        lines.append(f"   마감: {deadline}")
        if r.get(COL_REASON):
            lines.append(f"   이유: {r.get(COL_REASON)}")
        lines.append(f"   링크: {r.get(COL_URL,'')}")
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[리포트] {path} 생성 ({len(rows)}건)")
    return path


# ===========================================================================
# 텔레그램 전송
# ===========================================================================
def send_message(text, parse_mode=None):
    """짧은 텍스트 메시지 전송."""
    data = {"chat_id": _chat_id(), "text": text}
    if parse_mode:
        data["parse_mode"] = parse_mode
    try:
        resp = requests.post(_api("sendMessage"), data=data, timeout=20)
        ok = resp.ok and resp.json().get("ok", False)
        print(f"[텔레그램] 메시지 전송 {'성공' if ok else '실패'}")
        return ok
    except requests.RequestException as e:
        print(f"[텔레그램] 메시지 전송 오류: {e}")
        return False


def send_document(path, caption=""):
    """txt(또는 임의) 파일을 문서로 전송."""
    if not os.path.exists(path):
        print(f"[텔레그램] 파일 없음: {path}")
        return False
    try:
        with open(path, "rb") as fp:
            files = {"document": fp}
            data = {"chat_id": _chat_id(), "caption": caption}
            resp = requests.post(_api("sendDocument"), data=data, files=files, timeout=60)
        ok = resp.ok and resp.json().get("ok", False)
        print(f"[텔레그램] 문서 전송 {'성공' if ok else '실패'} ({path})")
        if not ok:
            print("   응답:", resp.text[:300])
        return ok
    except requests.RequestException as e:
        print(f"[텔레그램] 문서 전송 오류: {e}")
        return False


def send_report(rows, today_str=None):
    """OK 공고 리스트를 txt 1개로 만들어 전송. 0건이면 짧은 메시지로 대체."""
    today_str = today_str or date.today().isoformat()
    if not rows:
        return send_message(f"[{today_str}] 오늘 조건에 맞는 새 공고가 없습니다.")
    path = build_report_txt(rows, today_str=today_str)
    caption = f"오늘의 추천 채용공고 {len(rows)}건 ({today_str})"
    return send_document(path, caption=caption)


# ===========================================================================
# 단독 테스트 (연결 확인)
# ===========================================================================
if __name__ == "__main__":
    ok = send_message("[연결 테스트] telegram_send.py 정상 작동 확인")
    print("연결 테스트:", "성공" if ok else "실패")
