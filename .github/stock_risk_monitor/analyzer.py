"""
analyzer.py
───────────
Claude API 종합 분석 → 텔레그램 발송

GitHub Actions Secrets 키명:
  TELEGRAM_ETF_TOKEN    → 워크플로우에서 TELEGRAM_BOT_TOKEN 으로 주입
  TELEGRAM_ETF_CHAT_ID  → 워크플로우에서 TELEGRAM_CHAT_ID 로 주입
  ANTHROPIC_API_KEY     → 그대로 사용
"""

import os
import json
import requests
import anthropic
from datetime import datetime

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MSG_LEN  = 4000


# ──────────────────────────────────────────────
# Claude API 분석 (web_search 포함)
# ──────────────────────────────────────────────
def analyze_with_claude(data: dict) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    data_for_analysis = {k: v for k, v in data.items() if k != "earnings_news_prompt"}
    data_json = json.dumps(data_for_analysis, ensure_ascii=False, indent=2)

    system_prompt = """당신은 주식시장 리스크 분석 전문가입니다.
한국 반도체 대형주(삼성전자, SK하이닉스)의 주가 하락 리스크를 전문적으로 분석합니다.
분석은 반드시 한국어로, 텔레그램 메시지 형식(이모지 활용, 간결한 문체)으로 작성하세요.
숫자는 구체적으로 인용하고, 판단은 명확하게 내려주세요."""

    user_prompt = f"""
다음 데이터와 최신 뉴스를 종합하여 삼성전자·SK하이닉스의 주가 하락 리스크를 분석해주세요.

=== 수집된 시장 데이터 ===
{data_json}

=== 뉴스 검색 요청 ===
{data['earnings_news_prompt']}

=== 출력 형식 ===

📊 *[날짜] 반도체 대형주 리스크 모니터*

*① 📰 영업이익 영향 뉴스 (최근 1주)*
- 주요 뉴스 3~5개를 [긍정/부정/중립] 태그와 함께 요약

*② 📈 영업이익 컨센서스 추이*
- 삼성전자: Forward PER, EPS 추정치, DART 영업이익 현황
- SK하이닉스: Forward PER, EPS 추정치, DART 영업이익 현황
- 컨센서스 방향성 판단

*③ 🌏 매크로 변수 현황*
- 미국채 10년: [값]% (1주 [변동])
- 장단기 금리차: [값]pp
- 하이일드 스프레드: [값]bp (1주 [변동])
- 달러인덱스: [값]pt (1주 [변동])
- 종합 매크로 판단: [위험/중립/양호]

*④ 🔄 반도체 재고 순환 지표*
- 미국 전자부품 재고지수: 3개월/6개월 추이
- 삼성전자 재고자산: QoQ/YoY 변동
- SK하이닉스 재고자산: QoQ/YoY 변동
- 재고 사이클 위치: [정점/하강/저점/상승]

*⑤ 📉 필라델피아 반도체 지수 (SOX)*
- 현재: [값] | 1주 [%] | 1개월 [%]
- MA5 이격도: [값]% | 20일 변동성: [값]%
- 추세 판단: [상승/횡보/하락]

*🚨 종합 리스크 스코어*
① 뉴스: [0~5]점
② 컨센서스: [0~5]점
③ 매크로: [0~5]점
④ 재고사이클: [0~5]점
⑤ SOX: [0~5]점
합계: [합]/25점

*📌 결론*
- 종합 판단: [매우위험🔴 / 위험🟠 / 주의🟡 / 중립⚪ / 양호🟢]
- 삼성전자·하이닉스 단기(1~4주) 방향성
- 다음 주목 이벤트

리스크 스코어 15점 이상이면 결론에 반드시 "⚠️ 하락 경보" 포함.
""".strip()

    print("  🤖 Claude 분석 중 (web_search 포함)...")
    response = client.messages.create(
        model      = "claude-sonnet-4-20250514",
        max_tokens = 3000,
        system     = system_prompt,
        messages   = [{"role": "user", "content": user_prompt}],
        tools      = [{"type": "web_search_20250305", "name": "web_search"}],
    )

    full_text = "\n".join(
        block.text for block in response.content
        if hasattr(block, "text") and block.text
    )
    return full_text.strip()


# ──────────────────────────────────────────────
# 텔레그램 발송
# ──────────────────────────────────────────────
def send_telegram(message: str, parse_mode: str = "Markdown") -> bool:
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        raise ValueError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 환경변수 없음")

    url    = TELEGRAM_API.format(token=token)
    chunks = []
    msg    = message
    while len(msg) > MAX_MSG_LEN:
        pos = msg.rfind("\n", 0, MAX_MSG_LEN)
        if pos == -1:
            pos = MAX_MSG_LEN
        chunks.append(msg[:pos])
        msg = msg[pos:].lstrip()
    chunks.append(msg)

    success = True
    for i, chunk in enumerate(chunks):
        payload = {"chat_id": chat_id, "text": chunk, "parse_mode": parse_mode}
        try:
            r = requests.post(url, json=payload, timeout=15)
            r.raise_for_status()
            print(f"  ✅ 텔레그램 발송 ({i+1}/{len(chunks)})")
        except Exception as e:
            print(f"  ❌ Markdown 발송 실패, plain text 재시도: {e}")
            payload["parse_mode"] = ""
            try:
                r = requests.post(url, json=payload, timeout=15)
                r.raise_for_status()
                print(f"     → plain text 재발송 성공")
            except Exception as e2:
                print(f"     → plain text도 실패: {e2}")
                success = False
    return success


# ──────────────────────────────────────────────
# 하락 경보 별도 알림
# ──────────────────────────────────────────────
def send_alert_if_needed(analysis: str) -> None:
    if "하락 경보" in analysis or "⚠️" in analysis:
        alert = (
            "🔴🔴🔴 *긴급 하락 경보* 🔴🔴🔴\n\n"
            "삼성전자·SK하이닉스 리스크 스코어 위험 수준 도달!\n"
            "상세 보고서를 확인하세요."
        )
        send_telegram(alert)


# ──────────────────────────────────────────────
# 통합 실행
# ──────────────────────────────────────────────
def run_analysis_and_send(data: dict) -> str:
    print("🔍 Claude 종합 분석 시작...")
    analysis = analyze_with_claude(data)

    print("📤 텔레그램 발송 중...")
    send_telegram(analysis)

    if os.environ.get("ALERT_ON_RISK", "true").lower() == "true":
        send_alert_if_needed(analysis)

    print(f"🎉 완료 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    return analysis
