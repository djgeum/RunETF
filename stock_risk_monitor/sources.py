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


def _customs_call(key, strt, end, cnty=None):
    url = "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"
    params = {
        "serviceKey": key,
        "strtYymm":   strt,
        "endYymm":    end,
        "hsSgn":      C.KOREA_HS_CODE,
    }
    if cnty:
        params["cntyCd"] = cnty
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.content


def fetch_korea_export() -> dict:
    """
    HS 8542(전자집적회로) 월별 수출금액·물량 수집.
    조회기간이 1년 이내로 제한되므로 연도별로 나눠 호출하고,
    국가코드 필수 대응으로 전세계(합계) 우선, 실패 시 미국+중국 합산으로 폴백.
    """
    key = os.environ.get("SARAMIN_KEY", "")  # data.go.kr 키가 이 이름으로 등록됨
    if not key:
        print("    ✗ SARAMIN_KEY(data.go.kr) 없음 — 확인층 비활성")
        return {"value": pd.Series(dtype=float), "weight": pd.Series(dtype=float)}

    now = datetime.now()
    # 최근 26개월 커버를 위해 3개 연도 구간으로 분할
    periods = []
    for yr_back in range(0, 3):
        y = now.year - yr_back
        strt = f"{y}01"
        end  = f"{y}12" if yr_back > 0 else now.strftime("%Y%m")
        periods.append((strt, end))

    # 국가코드 후보: 전세계 합계코드 시도 → 실패 시 주요국 개별 합산
    # (data.go.kr 관세청은 전세계 합계에 'TO' 또는 공란을 쓰는 경우가 있어 순차 시도)
    country_plans = [None, "TO", "US", "CN"]

    merged = {}
    used_plan = None
    for plan in country_plans:
        got_any = False
        tmp = {}
        for strt, end in periods:
            try:
                content = _customs_call(key, strt, end, plan)
                part = _parse_customs_xml(content)
                if part:
                    got_any = True
                    for ym, d in part.items():
                        if ym not in tmp:
                            tmp[ym] = {"value": 0.0, "weight": 0.0}
                        tmp[ym]["value"]  += d["value"]
                        tmp[ym]["weight"] += d["weight"]
                time.sleep(0.3)
            except Exception as e:
                print(f"    ✗ 관세청 호출 실패 ({strt}-{end}, 국가={plan}): {e}")
        if got_any:
            merged = tmp
            used_plan = plan
            break

    if not merged:
        print("    ✗ 관세청: 모든 국가코드 시도 실패")
        return {"value": pd.Series(dtype=float), "weight": pd.Series(dtype=float)}

    print(f"    ℹ️ 관세청 조회 국가코드: {used_plan or '(공란=전세계)'}")
    vs = pd.Series({k: v["value"]  for k, v in merged.items()}).sort_index()
    ws = pd.Series({k: v["weight"] for k, v in merged.items()}).sort_index()
    vs = vs[vs > 0]
    ws = ws[ws > 0]
    _log(vs, "반도체 수출금액")
    _log(ws, "반도체 수출물량")
    return {"value": vs, "weight": ws}


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
        "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
