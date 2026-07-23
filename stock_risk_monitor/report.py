"""
report.py
─────────
판정 결과를 텔레그램 메시지로 조립하고 발송합니다.
숫자 판정은 100% 규칙 기반이며, Gemini는 뉴스 요약(선택)에만 사용됩니다.
"""

import os
import time
import requests
from datetime import datetime

MAX_MSG_LEN  = 3800
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
GEMINI_URL   = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"

BADGE = {
    "정상":  "🟢 정상",
    "주의":  "🟡 주의",
    "1단계": "🟠 1단계",
    "2단계": "🔴 2단계",
}

ACTION = {
    "정상":  "특이사항 없음. 기존 포지션 유지.",
    "주의":  "신규 진입 중단 / 비중 확대 금지. 매도는 하지 않음.",
    "1단계": "비중 축소, 레버리지 해제 검토.",
    "2단계": "현금화 확대. 반등 시마다 비중 축소.",
}

HEADLINE = {
    "정상":  "미국 시장 이상 신호 없음",
    "주의":  "미국 시장 내부 균열 감지 — 아직 매도 아님",
    "1단계": "자금 이탈 시작 — 방어 태세로 전환",
    "2단계": "한국 반도체 실물 둔화 확인 — 하락 추세 진입",
}


def fetch_news(gemini_model="gemini-3.5-flash") -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return ""
    today = datetime.now().strftime("%Y년 %m월 %d일")
    prompt = (
        f"오늘은 {today}입니다. 최근 1주일 내 아래를 웹 검색해 각 1줄로 요약:\n"
        "1) 미국 반도체·AI 관련 주요 뉴스 (엔비디아, AI 데이터센터 투자 동향)\n"
        "2) 삼성전자·SK하이닉스 메모리 가격/수요 뉴스\n"
        "3) 미 연준·금리·달러 관련 시장 이슈\n\n"
        "각 줄 앞에 [긍정]/[부정]/[중립] 태그. 총 3~5줄. 한국어만. 서론 없이 목록만."
    )
    try:
        r = requests.post(
            GEMINI_URL.format(m=gemini_model),
            headers={"Content-Type": "application/json", "x-goog-api-key": key},
            json={"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                  "tools": [{"google_search": {}}],
                  "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1000}},
            timeout=120)
        r.raise_for_status()
        parts = r.json()["candidates"][0]["content"]["parts"]
        return "\n".join(p.get("text", "") for p in parts if p.get("text")).strip()
    except Exception as e:
        print(f"    ⚠️ 뉴스 요약 실패 (계속 진행): {e}")
        return ""


def _line(s):
    mark = "🔴" if s.fired else "⚪"
    base = f"{mark} {s.name}: {s.value}"
    if s.asof and s.asof != "N/A":
        base += f"  [{s.asof}]"
    return base


def build_message(verdict, data, news="") -> str:
    L = []
    today = datetime.now().strftime("%Y-%m-%d (%a)")

    L.append(f"📊 미국시장 리스크 모니터  {today}")
    L.append("")
    L.append(f"▶ {BADGE.get(verdict.level, verdict.level)}  {HEADLINE.get(verdict.level,'')}")
    L.append("")
    L.append(f"👉 {ACTION.get(verdict.level,'')}")
    if verdict.released:
        L.append(f"   ({verdict.released})")
    L.append("")

    # 선행층
    L.append("━━ 선행 · 다이버전스 ━━")
    for s in verdict.div_signals:
        L.append(_line(s))
    L.append("")

    # 동행층
    L.append("━━ 동행 · 매크로 스트레스 ━━")
    for s in verdict.macro_signals:
        L.append(_line(s))
    L.append("")

    # 확인층
    L.append("━━ 확인 · 한국 반도체 수출 ━━")
    for s in verdict.kr_signals:
        L.append(_line(s))
    L.append("")

    L.append(f"판정 근거: {verdict.reason}")
    L.append("")

    if news:
        L.append("━━ 뉴스 요약 ━━")
        L.append(news)
        L.append("")

    L.append(f"수집: {data.get('collected_at','')}  |  FRED·Yahoo·관세청")
    return "\n".join(L)


def send_telegram(message: str) -> bool:
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        raise ValueError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 없음")

    url = TELEGRAM_API.format(token=token)
    chunks, msg = [], message
    while len(msg) > MAX_MSG_LEN:
        pos = msg.rfind("\n", 0, MAX_MSG_LEN)
        pos = pos if pos != -1 else MAX_MSG_LEN
        chunks.append(msg[:pos]); msg = msg[pos:].lstrip()
    chunks.append(msg)

    ok = True
    for i, chunk in enumerate(chunks, 1):
        try:
            r = requests.post(url, json={"chat_id": chat_id, "text": chunk}, timeout=20)
            r.raise_for_status()
            print(f"    ✅ 텔레그램 발송 ({i}/{len(chunks)})")
        except Exception as e:
            print(f"    ❌ 발송 실패 ({i}/{len(chunks)}): {e}")
            ok = False
        time.sleep(0.4)
    return ok


def send_alert(verdict) -> None:
    """1단계 이상일 때 짧은 선행 경보"""
    if verdict.level in ("정상", "주의"):
        return
    send_telegram(f"{BADGE[verdict.level]} 리스크 {verdict.level} — {HEADLINE[verdict.level]}\n\n"
                  f"{ACTION[verdict.level]}\n\n상세 리포트가 이어집니다.")
