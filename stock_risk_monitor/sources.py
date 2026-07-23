"""
sources.py
──────────
외부 데이터 수집 전담. 판정은 하지 않고 시계열(pandas Series)만 반환합니다.
각 소스는 실패해도 빈 Series를 돌려주어 전체 파이프라인이 멈추지 않게 합니다.
"""

import os
import time
import warnings
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta

import requests
import pandas as pd
import yfinance as yf
from fredapi import Fred

import config as C

warnings.filterwarnings("ignore")


def _log(s: pd.Series, label: str) -> pd.Series:
    if s is not None and len(s):
        print(f"    ✓ {label}: {len(s)}건 (최신 {str(s.index[-1])[:10]})")
    else:
        print(f"    ✗ {label}: 데이터 없음")
    return s


# ══════════════════════════════════════════════
# FRED
# ══════════════════════════════════════════════
def fetch_fred() -> dict:
    key = os.environ.get("FRED_API_KEY", "")
    if not key:
        print("    ✗ FRED_API_KEY 없음")
        return {"hy": pd.Series(dtype=float), "us10y": pd.Series(dtype=float)}

    fred  = Fred(api_key=key)
    start = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")

    def g(sid, label):
        try:
            return _log(fred.get_series(sid, observation_start=start).dropna(), label)
        except Exception as e:
            print(f"    ✗ {label} 실패: {e}")
            return pd.Series(dtype=float)

    return {"hy": g("BAMLH0A0HYM2", "하이일드 OAS"),
            "us10y": g("DGS10", "미국채 10Y")}


# ══════════════════════════════════════════════
# Yahoo Finance
# ══════════════════════════════════════════════
def fetch_market() -> dict:
    start = (datetime.now() - timedelta(days=500)).strftime("%Y-%m-%d")

    def g(ticker, label):
        try:
            raw = yf.download(ticker, start=start, progress=False, auto_adjust=False)
            return _log(raw["Close"].squeeze().dropna(), label)
        except Exception as e:
            print(f"    ✗ {label} 실패: {e}")
            return pd.Series(dtype=float)

    return {"spy": g("SPY", "S&P500 ETF"),
            "rsp": g("RSP", "S&P500 등가중"),
            "sox": g("^SOX", "필라델피아 반도체"),
            "dxy": g("DX-Y.NYB", "달러인덱스")}


# ══════════════════════════════════════════════
# 관세청(data.go.kr): 반도체 수출금액·물량
# ══════════════════════════════════════════════
def _parse_customs_xml(content: bytes) -> dict:
    """관세청 XML → {'YYYY-MM': {'value':..,'weight':..}}"""
    rows = {}
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        print(f"    ✗ 관세청 XML 파싱 실패: {e}")
        return rows

    # 오류 메시지 확인
    rc  = root.findtext(".//resultCode") or root.findtext(".//cmmMsgHeader/returnReasonCode")
    msg = root.findtext(".//resultMsg")  or root.findtext(".//cmmMsgHeader/errMsg")
    if rc and rc not in ("00", "0"):
        print(f"    ⚠️ 관세청 오류코드 {rc}: {msg}")

    for item in root.iter("item"):
        raw_ym = (item.findtext("year") or "").replace(".", "").strip()
        if len(raw_ym) < 6 or not raw_ym[:6].isdigit():
            continue
        ym = f"{raw_ym[:4]}-{raw_ym[4:6]}"
        try:
            v = float((item.findtext("expDlr") or "0").replace(",", ""))
            w = float((item.findtext("expWgt") or "0").replace(",", ""))
        except ValueError:
            continue
        # 같은 월에 여러 국가행이 오면 합산 (전세계 집계 대비)
        if ym not in rows:
            rows[ym] = {"value": 0.0, "weight": 0.0}
        rows[ym]["value"]  += v
        rows[ym]["weight"] += w
    return rows


def _customs_call(key, strt, end, cnty, scheme="https", hs=None):
    """
    관세청 단일 호출.
    data.go.kr 인증키는 Encoding/Decoding 두 종류가 배포되는데,
    Encoding 키를 requests params에 그대로 넣으면 이중 인코딩되어 인증 실패합니다.
    unquote로 항상 디코딩 형태로 정규화해 전달합니다.
    """
    url = f"{scheme}://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"
    params = {
        "serviceKey": unquote(key),
        "strtYymm":   strt,
        "endYymm":    end,
        "hsSgn":      hs or C.KOREA_HS_CODE,
        "cntyCd":     cnty,
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.content


# 관세청(제공기관) 응답코드 → 원인 설명
CUSTOMS_CODE_HINT = {
    "00": "정상",
    "01": "서비스 시스템 오류 (제공기관 장애 — 잠시 후 재시도)",
    "02": "인증키가 파라미터에 없음 (serviceKey 미전달)",
    "03": "인증키가 올바르지 않음 (Decoding 키 사용 여부 / 활용신청 승인 확인)",
    "04": "필수 요청변수 누락 (strtYymm, endYymm, cntyCd 확인)",
}

# 게이트웨이 레벨 오류코드 (data.go.kr 공통)
GW_CODE_HINT = {
    "20": "서비스 접근 거부 — 활용신청 미승인 상태",
    "22": "일일 트래픽 한도 초과",
    "30": "등록되지 않은 서비스키",
    "31": "활용기간 만료",
    "32": "등록되지 않은 IP",
}


def _diagnose_response(content: bytes) -> str:
    """응답에서 오류 코드/메시지를 뽑아 원인 설명까지 붙여 반환"""
    text  = content.decode("utf-8", errors="replace")
    hints = []
    codes = {}

    for tag in ("resultCode", "resultMsg", "returnReasonCode",
                "returnAuthMsg", "errMsg"):
        i = text.find(f"<{tag}>")
        if i != -1:
            j = text.find(f"</{tag}>", i)
            if j != -1:
                val = text[i + len(tag) + 2:j].strip()[:80]
                codes[tag] = val
                hints.append(f"{tag}={val}")

    # 원인 해설 부착
    rc = codes.get("resultCode", "").zfill(2) if codes.get("resultCode", "").isdigit() else ""
    if rc in CUSTOMS_CODE_HINT:
        hints.append(f"→ {CUSTOMS_CODE_HINT[rc]}")
    gw = codes.get("returnReasonCode", "")
    if gw in GW_CODE_HINT:
        hints.append(f"→ {GW_CODE_HINT[gw]}")

    if not hints:
        hints.append(text[:160].replace("\n", " "))
    return " | ".join(hints)


def _year_periods(now: datetime, years_back: int = 3):
    """조회기간 1년 제한 대응: 연도별 구간으로 분할"""
    periods = []
    for back in range(years_back):
        y = now.year - back
        strt = f"{y}01"
        end  = now.strftime("%Y%m") if back == 0 else f"{y}12"
        periods.append((strt, end))
    return periods


def fetch_korea_export() -> dict:
    """
    HS 8542(전자집적회로) 월별 수출금액·물량 수집.
    관세청 API는 전세계 합계를 지원하지 않으므로 주요 수출상대국을
    개별 조회한 뒤 월별로 합산합니다.
    """
    key = os.environ.get("SARAMIN_KEY", "")  # data.go.kr 키가 이 이름으로 등록됨
    empty = {"value": pd.Series(dtype=float), "weight": pd.Series(dtype=float),
             "coverage": [], "note": ""}
    if not key:
        print("    x SARAMIN_KEY(data.go.kr) 없음 - 확인층 비활성")
        empty["note"] = "인증키 미설정"
        return empty

    now     = datetime.now()
    periods = _year_periods(now)

    # ── 사전 점검: 첫 호출로 https/http 및 응답 형식 확인 ──
    scheme   = "https"
    hs_used  = C.KOREA_HS_CODE
    probe_ok = False
    probe_msg = ""
    hs_candidates = [C.KOREA_HS_CODE]
    if getattr(C, "KOREA_HS_FALLBACK", None):
        hs_candidates.append(C.KOREA_HS_FALLBACK)

    for hs in hs_candidates:
        for sch in ("https", "http"):
            try:
                content = _customs_call(key, periods[0][0], periods[0][1],
                                        C.KOREA_COUNTRIES[0], sch, hs)
                diag   = _diagnose_response(content)
                parsed = _parse_customs_xml(content)
                if parsed:
                    scheme, hs_used, probe_ok = sch, hs, True
                    sample = sorted(parsed.items())[-1]
                    print(f"    i 관세청 접속 확인 ({sch}) HS={hs} | {diag}")
                    print(f"      샘플: {C.KOREA_COUNTRIES[0]} {sample[0]} "
                          f"수출 ${sample[1]['value']:,.0f} / "
                          f"{sample[1]['weight']:,.0f}kg "
                          f"(단가 ${sample[1]['value']/sample[1]['weight']:,.0f}/kg)"
                          if sample[1]['weight'] else "")
                    break
                probe_msg = f"HS={hs} {diag} | item {content.count(b'<item>')}개 (유효 월데이터 0)"
            except Exception as e:
                probe_msg = f"HS={hs} {sch} 예외: {e}"
        if probe_ok:
            break

    if hs_used != C.KOREA_HS_CODE:
        print(f"    ! 주 코드({C.KOREA_HS_CODE}) 데이터 없음 → 폴백 {hs_used} 사용")

    if not probe_ok:
        print(f"    x 관세청 사전 점검 실패 - {probe_msg}")
        print("      점검 항목:")
        print("        1) data.go.kr 마이페이지 > 활용신청 현황 > 처리상태 '승인' 확인")
        print("        2) 활용기간 시작일이 오늘 이후가 아닌지 확인")
        print("        3) GitHub Secret 값이 '일반 인증키'와 일치하는지 확인")
        empty["note"] = probe_msg[:120]
        return empty

    merged = {}
    ok_list, fail_list = [], []

    for cnty in C.KOREA_COUNTRIES:
        got = False
        for strt, end in periods:
            try:
                content = _customs_call(key, strt, end, cnty, scheme, hs_used)
                part    = _parse_customs_xml(content)
                for ym, d in part.items():
                    if ym not in merged:
                        merged[ym] = {"value": 0.0, "weight": 0.0}
                    merged[ym]["value"]  += d["value"]
                    merged[ym]["weight"] += d["weight"]
                if part:
                    got = True
            except Exception as e:
                print(f"    x 관세청 호출 실패 ({cnty} {strt}-{end}): {e}")
            time.sleep(C.KOREA_CALL_SLEEP)
        (ok_list if got else fail_list).append(cnty)

    print(f"    i 수집 성공 {len(ok_list)}개국: {','.join(ok_list) or '-'}")
    if fail_list:
        print(f"    ! 수집 실패 {len(fail_list)}개국: {','.join(fail_list)}")

    if not merged or len(fail_list) > C.KOREA_MAX_FAIL:
        print("    x 관세청: 유효 데이터 부족 - 확인층 비활성")
        empty["coverage"] = ok_list
        empty["note"] = f"수집국 {len(ok_list)}개로 부족"
        return empty

    vs = pd.Series({k: v["value"]  for k, v in merged.items()}).sort_index()
    ws = pd.Series({k: v["weight"] for k, v in merged.items()}).sort_index()
    vs = vs[vs > 0]
    ws = ws[ws > 0]

    # 최신월은 집계 진행중일 수 있어 직전월 대비 급감하면 제외
    if len(vs) >= 2 and vs.iloc[-1] < vs.iloc[-2] * 0.5:
        dropped = vs.index[-1]
        print(f"    ! 최신월 {dropped} 집계 미완료로 판단하여 제외")
        vs = vs.iloc[:-1]
        ws = ws[ws.index != dropped]

    _log(vs, "반도체 수출금액")
    _log(ws, "반도체 수출물량")
    return {"value": vs, "weight": ws, "coverage": ok_list,
            "note": "", "hs": hs_used}


# ══════════════════════════════════════════════
# 통합
# ══════════════════════════════════════════════
def collect_all() -> dict:
    print("  📡 FRED 수집...")
    fred = fetch_fred()
    print("  📈 시장 데이터 수집...")
    mkt = fetch_market()
    print("  🇰🇷 관세청 반도체 수출 수집...")
    kr = fetch_korea_export()

    return {
        "hy": fred["hy"], "us10y": fred["us10y"],
        "spy": mkt["spy"], "rsp": mkt["rsp"], "sox": mkt["sox"], "dxy": mkt["dxy"],
        "kr_value": kr["value"], "kr_weight": kr["weight"],
        "kr_coverage": kr.get("coverage", []),
        "kr_note": kr.get("note", ""),
        "kr_hs": kr.get("hs", ""),
        "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
