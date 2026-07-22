"""
analyzer.py  (Gemini 버전)
──────────────────────────
Google Gemini API로 리스크 종합 분석 → 텔레그램 발송

환경변수:
  GEMINI_API_KEY      : Google AI Studio 발급 (무료 티어 있음)
  TELEGRAM_BOT_TOKEN  : GitHub Secret TELEGRAM_ETF_TOKEN 에서 주입
  TELEGRAM_CHAT_ID    : GitHub Secret TELEGRAM_ETF_CHAT_ID 에서 주입
  ALERT_ON_RISK       : "true" 면 하락 경보 시 추가 알림
"""

import os
import json
import time
import requests
from datetime import datetime

# ── Gemini 설정 ──
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
GEMINI_URL   = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)

# ── 텔레그램 설정 ──
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MSG_LEN  = 4000


# ══════════════════════════════════════════════
# Gemini API 호출
# ══════════════════════════════════════════════
def call_gemini(prompt: str, system_instruction: str = "",
                use_search: bool = True, retries: int = 3) -> str:
    """Gemini generateContent 호출 (Google Search grounding 포함)"""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 환경변수가 없습니다.")

    url = GEMINI_URL.format(model=GEMINI_MODEL)

    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature":     0.3,
            "maxOutputTokens": 4096,
        },
    }

    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    if use_search:
        payload["tools"] = [{"google_search": {}}]

    headers = {
        "Content-Type":  "application/json",
        "x-goog-api-key": api_key,
    }

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            print(f"  🤖 Gemini 호출 중... (시도 {attempt}/{retries})")
            resp = requests.post(url, headers=headers, json=payload, timeout=180)

            if resp.status_code == 429:
                wait = 20 * attempt
                print(f"     ⏳ 레이트리밋 — {wait}초 대기 후 재시도")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            data = resp.json()

            # 응답 텍스트 추출
            candidates = data.get("candidates", [])
            if not candidates:
                raise ValueError(f"응답에 candidates 없음: {json.dumps(data)[:400]}")

            parts = candidates[0].get("content", {}).get("parts", [])
            text  = "\n".join(p.get("text", "") for p in parts if p.get("text"))

            if not text.strip():
                raise ValueError(f"빈 응답: {json.dumps(candidates[0])[:400]}")

            # 검색 출처 표시 (grounding 사용 시 권장)
            gm = candidates[0].get("groundingMetadata", {})
            chunks = gm.get("groundingChunks", [])
            if chunks:
                sources = []
                for c in chunks[:5]:
                    web = c.get("web", {})
                    title = web.get("title", "")
                    if title:
                        sources.append(f"• {title}")
                if sources:
                    text += "\n\n📎 참고 출처\n" + "\n".join(sources)

            return text.strip()

        except requests.exceptions.HTTPError as e:
            last_err = e
            body = getattr(e.response, "text", "")[:400]
            print(f"     ❌ HTTP 오류: {e} | {body}")
            if attempt < retries:
                time.sleep(10 * attempt)
        except Exception as e:
            last_err = e
            print(f"     ❌ 오류: {e}")
            if attempt < retries:
                time.sleep(10 * attempt)

    raise RuntimeError(f"Gemini 호출 {retries}회 모두 실패: {last_err}")


# ══════════════════════════════════════════════
# 리스크 종합 분석
# ══════════════════════════════════════════════
def analyze_with_gemini(data: dict) -> str:
    data_for_analysis = {k: v for k, v in data.items() if k != "earnings_news_prompt"}
    data_json = json.dumps(data_for_analysis, ensure_ascii=False, indent=2)

    system_instruction = (
        "당신은 주식시장 리스크 분석 전문가입니다. "
        "한국 반도체 대형주(삼성전자, SK하이닉스)의 주가 하락 리스크를 분석합니다. "
        "반드시 한국어로, 텔레그램 메시지 형식(이모지 활용, 간결한 문체)으로 작성하세요. "
        "숫자는 구체적으로 인용하고 판단은 명확히 내리세요. "
        "마크다운 표(|) 대신 줄바꿈 리스트를 사용하세요."
    )

    prompt = f"""
아래 시장 데이터와 최신 뉴스를 종합해 삼성전자·SK하이닉스의 주가 하락 리스크를 분석하세요.

=== 수집된 시장 데이터 ===
{data_json}

=== 뉴스 검색 요청 (Google Search 활용) ===
{data['earnings_news_prompt']}

=== 출력 형식 (반드시 준수) ===

📊 {datetime.now().strftime('%Y-%m-%d')} 반도체 대형주 리스크 모니터

① 📰 영업이익 영향 뉴스 (최근 1주)
- 주요 뉴스 3~5개를 [긍정/부정/중립] 태그와 함께 한 줄씩 요약

② 📈 영업이익 컨센서스 추이
- 삼성전자: Forward PER, EPS 추정, DART 영업이익 현황
- SK하이닉스: Forward PER, EPS 추정, DART 영업이익 현황
- 컨센서스 방향성: [상향/하향/유지]

③ 🌏 매크로 변수 현황
- 미국채 10년: [값]% (1주 [변동])
- 장단기 금리차: [값]pp
- 하이일드 스프레드: [값]bp (1주 [변동])
- 달러인덱스: [값]pt (1주 [변동])
- 매크로 종합: [위험/중립/양호]

④ 🔄 반도체 재고 순환
- 미국 전자부품 재고지수: 3개월/6개월 추이
- 삼성전자 재고자산: QoQ [값]% / YoY [값]%
- SK하이닉스 재고자산: QoQ [값]% / YoY [값]%
- 재고 사이클 위치: [정점/하강/저점/상승]

⑤ 📉 필라델피아 반도체 지수 (SOX)
- 현재 [값] | 1주 [%] | 1개월 [%]
- MA5 이격도 [값]% | 20일 변동성 [값]%
- 추세: [상승/횡보/하락]

🚨 종합 리스크 스코어 (각 0~5점, 높을수록 위험)
① 뉴스: ?점
② 컨센서스: ?점
③ 매크로: ?점
④ 재고사이클: ?점
⑤ SOX: ?점
━━━━━━━━━━━━
합계: ?/25점

📌 결론
- 종합 판단: [매우위험🔴 / 위험🟠 / 주의🟡 / 중립⚪ / 양호🟢]
- 단기(1~4주) 방향성 전망
- 다음 주목 이벤트

※ 합계 15점 이상이면 결론에 반드시 "⚠️ 하락 경보" 문구를 포함하세요.
""".strip()

    return call_gemini(prompt, system_instruction, use_search=True)


# ══════════════════════════════════════════════
# 텔레그램 발송
# ══════════════════════════════════════════════
def send_telegram(message: str, parse_mode: str = "") -> bool:
    """텔레그램 발송 (기본 plain text — Gemini 출력은 마크다운 파싱 오류가 잦음)"""
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        raise ValueError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 환경변수 없음")

    url = TELEGRAM_API.format(token=token)

    # 4000자 단위 분할
    chunks, msg = [], message
    while len(msg) > MAX_MSG_LEN:
        pos = msg.rfind("\n", 0, MAX_MSG_LEN)
        if pos == -1:
            pos = MAX_MSG_LEN
        chunks.append(msg[:pos])
        msg = msg[pos:].lstrip()
    chunks.append(msg)

    ok = True
    for i, chunk in enumerate(chunks, 1):
        payload = {"chat_id": chat_id, "text": chunk}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            r = requests.post(url, json=payload, timeout=20)
            r.raise_for_status()
            print(f"  ✅ 텔레그램 발송 ({i}/{len(chunks)})")
        except Exception as e:
            print(f"  ❌ 발송 실패 ({i}/{len(chunks)}): {e}")
            ok = False
        time.sleep(0.5)   # 텔레그램 레이트리밋 방지
    return ok


def send_alert_if_needed(analysis: str) -> None:
    if "하락 경보" in analysis:
        send_telegram(
            "🔴🔴🔴 긴급 하락 경보 🔴🔴🔴\n\n"
            "삼성전자·SK하이닉스 리스크 스코어가 위험 수준에 도달했습니다.\n"
            "위 상세 보고서를 확인하세요."
        )


# ══════════════════════════════════════════════
# 통합 실행
# ══════════════════════════════════════════════
def run_analysis_and_send(data: dict) -> str:
    print("🔍 Gemini 종합 분석 시작...")
    analysis = analyze_with_gemini(data)

    print("📤 텔레그램 발송 중...")
    send_telegram(analysis)

    if os.environ.get("ALERT_ON_RISK", "true").lower() == "true":
        send_alert_if_needed(analysis)

    print(f"🎉 완료 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    return analysis
