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


def build_message(verdict, data, news="", val=None) -> str:
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
    cov  = data.get("kr_coverage", [])
    note = data.get("kr_note", "")
    hs   = data.get("kr_hs", "")
    hs_label = {"854232": "메모리", "854231": "프로세서", "8542": "반도체전체"}.get(hs, hs)
    if cov:
        L.append(f"HS {hs}({hs_label}) · {len(cov)}개국: {','.join(cov)}")
    else:
        L.append(f"수집 실패 — 확인층 비활성{(' (' + note + ')') if note else ''}")
    for s in verdict.kr_signals:
        L.append(_line(s))
    L.append("")

    L.append(f"판정 근거: {verdict.reason}")
    L.append("")

    if news:
        L.append("━━ 뉴스 요약 ━━")
        L.append(news)
        L.append("")

    # ── KOSPI 밸류에이션 (독립 참고 정보) ──
    if val is not None:
        L.append("━━ KOSPI 밸류에이션 (참고) ━━")
        if val.ok:
            L.append(f"현재 지수: {val.index_now:,.0f} (PBR {val.pbr_now:.2f})")
            gtxt = f"성장률 {val.growth:+.1f}% 반영" if val.growth else "성장률 미반영"
            L.append(f"조정 PBR(중심): {val.pbr_center:.2f} · {gtxt}")
            L.append(f"역사적: 평균 {val.pbr_mean:.2f} ± {val.pbr_sigma:.2f} ({val.years}년)")
            L.append(f"이격율: {val.dispersion:+.0f}% ({val.label})")
            if val.index_center:
                L.append(f"적정 지수: 중심 {val.index_center:,.0f} / "
                         f"하단 {val.index_lower:,.0f} / 상단 {val.index_upper:,.0f}")

            # ── 성장률 진단 상세 ──
            d = val.diag or {}
            if d.get("growth"):
                g = d["growth"]; p = d["past"]; n = d["now"]
                L.append("")
                L.append("─ 성장률 진단 ─")
                L.append(f"[{d.get('past_date','1년전')}] 지수 {p['idx']:,.0f} · "
                         f"PER {p['per']:.1f} · PBR {p['pbr']:.2f}")
                L.append(f"[{d.get('now_date','현재')}] 지수 {n['idx']:,.0f} · "
                         f"PER {n['per']:.1f} · PBR {n['pbr']:.2f}")
                L.append(f"지수 {g['idx']:+.1f}% | EPS {g['eps']:+.1f}% | "
                         f"BPS {g['bps']:+.1f}% | PER {g['per']:+.1f}%")
                if d.get("capped"):
                    L.append(f"※ EPS 성장률이 상식범위 초과로 미반영됨")
                else:
                    L.append(f"※ EPS 성장률 {g['eps']:+.1f}% 반영 (중심선 상향)")
                # 해석 한 줄
                if g["eps"] < g["idx"]:
                    L.append("해석: 주가가 실적보다 더 오름 → 밸류에이션 확장")
                else:
                    L.append("해석: 실적이 주가보다 빠름 → 밸류에이션 매력")
        elif val.login_failed:
            L.append("⚠️ KRX 로그인 실패 — 비밀번호 갱신이 필요할 수 있습니다.")
            L.append("   KRX 사이트에서 비번 변경 후 GitHub Secret(KRX_USER_PW) 업데이트")
        else:
            L.append(f"데이터 없음 ({val.note})")
        L.append("")

    L.append(f"수집: {data.get('collected_at','')}  |  FRED·Yahoo·관세청·KRX")
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
