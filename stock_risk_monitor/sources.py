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


def _customs_call(key, strt, end, cnty):
    """관세청 단일 호출 (국가코드 필수)"""
    url = "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"
    params = {
        "serviceKey": key,
        "strtYymm":   strt,
        "endYymm":    end,
        "hsSgn":      C.KOREA_HS_CODE,
        "cntyCd":     cnty,
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.content


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
    if not key:
        print("    x SARAMIN_KEY(data.go.kr) 없음 - 확인층 비활성")
        return {"value": pd.Series(dtype=float), "weight": pd.Series(dtype=float),
                "coverage": []}

    now      = datetime.now()
    periods  = _year_periods(now)
    merged   = {}
    ok_list, fail_list = [], []

    for cnty in C.KOREA_COUNTRIES:
        got = False
        for strt, end in periods:
            try:
                content = _customs_call(key, strt, end, cnty)
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

    print(f"    i 수집 성공 {len(ok_list)}개국: {','.join(ok_list)}")
    if fail_list:
        print(f"    ! 수집 실패 {len(fail_list)}개국: {','.join(fail_list)}")

    if not merged or len(fail_list) > C.KOREA_MAX_FAIL:
        print("    x 관세청: 유효 데이터 부족 - 확인층 비활성")
        return {"value": pd.Series(dtype=float), "weight": pd.Series(dtype=float),
                "coverage": ok_list}

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
    return {"value": vs, "weight": ws, "coverage": ok_list}


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
        "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
