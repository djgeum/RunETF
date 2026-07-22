"""
data_collector.py
─────────────────
각 리스크 항목별 데이터 수집 모듈

환경변수 키명:
  FRED_API_KEY        : FRED (미국채금리, 하이일드 스프레드)
  DART_API_KEY        : DART OpenAPI (영업이익 컨센서스)
  ANTHROPIC_API_KEY   : Claude 분석 (analyzer.py에서 사용)
  TELEGRAM_BOT_TOKEN  : analyzer.py에서 사용 (= TELEGRAM_ETF_TOKEN secret)
  TELEGRAM_CHAT_ID    : analyzer.py에서 사용 (= TELEGRAM_ETF_CHAT_ID secret)
"""

import os
import warnings
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from fredapi import Fred

warnings.filterwarnings("ignore")


# ──────────────────────────────────────────────
# 공통 유틸
# ──────────────────────────────────────────────
def get_fred_client() -> Fred:
    key = os.environ.get("FRED_API_KEY", "")
    if not key:
        raise ValueError("FRED_API_KEY 환경변수가 없습니다.")
    return Fred(api_key=key)


def series_summary(series: pd.Series, label: str, unit: str = "%") -> dict:
    """시계열 → 현재값·변동·변동률·최고최저 요약"""
    if series is None or series.empty:
        return {"오류": f"{label} 데이터 없음"}
    s = series.dropna()
    if s.empty:
        return {"오류": f"{label} 유효 데이터 없음"}
    latest = float(s.iloc[-1])
    w_ago  = float(s.iloc[-6]) if len(s) >= 6 else float(s.iloc[0])
    m_ago  = float(s.iloc[0])
    return {
        "현재값":          round(latest, 4),
        "단위":            unit,
        "1주_변동":        round(latest - w_ago, 4),
        "1개월_변동":      round(latest - m_ago, 4),
        "1주_변동률(%)":   round((latest - w_ago)  / abs(w_ago)  * 100, 2) if w_ago  else None,
        "1개월_변동률(%)": round((latest - m_ago)  / abs(m_ago)  * 100, 2) if m_ago  else None,
        "최근30일_최고":   round(float(s.max()), 4),
        "최근30일_최저":   round(float(s.min()), 4),
        "기준일":          str(s.index[-1])[:10],
    }


# ──────────────────────────────────────────────
# 1. 영업이익 관련 뉴스 → Claude web_search 프롬프트
# ──────────────────────────────────────────────
def get_earnings_news_prompt() -> str:
    today = datetime.now().strftime("%Y년 %m월 %d일")
    return f"""
오늘은 {today}입니다.
최근 1주일 내 다음 항목을 웹에서 검색하고 요약해주세요:

1. 삼성전자(005930)·SK하이닉스(000660) 영업이익 전망 변화 뉴스
2. 반도체 수요/공급 동향 (AI 데이터센터, PC, 스마트폰)
3. 주요 고객사 동향 (NVIDIA, AMD, Apple, TSMC 등)
4. 한국 반도체 수출 통계 및 정부 발표

각 항목을 3줄 이내로 요약하고 영향을 [긍정/부정/중립]으로 표시.
반드시 한국어로 답변.
""".strip()


# ──────────────────────────────────────────────
# 2. 영업이익 컨센서스 추이 (DART OpenAPI + Yahoo Finance 보완)
# ──────────────────────────────────────────────
DART_CORP_CODES = {
    "삼성전자":   "00126380",
    "SK하이닉스": "00164779",
}
DART_STOCK_CODES = {
    "삼성전자":   "005930",
    "SK하이닉스": "000660",
}

def _dart_financial(corp_code: str, year: str, report_code: str = "11011") -> list | None:
    """
    DART 단일회사 주요계정 조회
    report_code: 11011=사업보고서, 11012=반기, 11013=1분기, 11014=3분기
    """
    dart_key = os.environ.get("DART_API_KEY", "")
    if not dart_key:
        return None
    url = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"
    params = {
        "crtfc_key":  dart_key,
        "corp_code":  corp_code,
        "bsns_year":  year,
        "reprt_code": report_code,
        "fs_div":     "CFS",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("status") == "000":
            return data.get("list", [])
    except Exception as e:
        print(f"    [DART] {corp_code} 조회 실패: {e}")
    return None


def _extract_op_income(items: list) -> float | None:
    """DART 응답에서 영업이익 추출"""
    if not items:
        return None
    for item in items:
        acnt_nm = item.get("account_nm", "")
        if "영업이익" in acnt_nm and "손실" not in acnt_nm:
            try:
                val = item.get("thstrm_amount", "").replace(",", "")
                return float(val) if val else None
            except Exception:
                pass
    return None


def get_consensus_data() -> dict:
    """DART 실적 + Yahoo Finance 컨센서스 통합"""
    result = {}
    current_year = str(datetime.now().year)
    prev_year    = str(datetime.now().year - 1)

    for name, corp_code in DART_CORP_CODES.items():
        ticker = DART_STOCK_CODES[name] + ".KS"
        entry  = {}

        # ① DART 전년도 사업보고서
        prev_items = _dart_financial(corp_code, prev_year, "11011")
        op_prev    = _extract_op_income(prev_items)
        if op_prev is not None:
            entry["영업이익_전년도(억원)"] = round(op_prev / 1e8)

        # ② DART 당해 3분기 누적
        q3_items = _dart_financial(corp_code, current_year, "11014")
        op_q3    = _extract_op_income(q3_items)
        if op_q3 is not None:
            entry["영업이익_당해누적3Q(억원)"] = round(op_q3 / 1e8)

        # ③ YoY 추정
        if op_prev and op_q3:
            base = op_prev * 0.75
            entry["YoY_3Q누적_성장률(%)"] = round((op_q3 - base) / abs(base) * 100, 1)

        # ④ Yahoo Finance 보완
        try:
            t    = yf.Ticker(ticker)
            info = t.info
            entry["현재가"]        = info.get("currentPrice") or info.get("regularMarketPrice")
            entry["PER_Trailing"]  = info.get("trailingPE")
            entry["PER_Forward"]   = info.get("forwardPE")
            entry["52주_최고"]     = info.get("fiftyTwoWeekHigh")
            entry["52주_최저"]     = info.get("fiftyTwoWeekLow")
            ee = t.earnings_estimate
            if ee is not None and not ee.empty and "avg" in ee.columns:
                entry["EPS_추정_올해"] = ee.loc["0y",  "avg"] if "0y"  in ee.index else None
                entry["EPS_추정_내년"] = ee.loc["+1y", "avg"] if "+1y" in ee.index else None
        except Exception as e:
            entry["yahoo_오류"] = str(e)

        result[name] = entry

    return result


# ──────────────────────────────────────────────
# 3. 외부 매크로 변수 (FRED API)
# ──────────────────────────────────────────────
def get_macro_data() -> dict:
    fred  = get_fred_client()
    end   = datetime.now()
    start = end - timedelta(days=40)

    def fetch(series_id: str, label: str) -> pd.Series:
        try:
            return fred.get_series(series_id, observation_start=start, observation_end=end)
        except Exception as e:
            print(f"    [FRED] {label} 실패: {e}")
            return pd.Series(dtype=float)

    us10y     = fetch("DGS10",        "미국채 10년")
    us2y      = fetch("DGS2",         "미국채 2년")
    hy_spread = fetch("BAMLH0A0HYM2", "하이일드 스프레드")

    try:
        dxy = yf.download("DX-Y.NYB",
                          start=start.strftime("%Y-%m-%d"),
                          end=end.strftime("%Y-%m-%d"),
                          progress=False)["Close"].squeeze().dropna()
    except Exception:
        dxy = pd.Series(dtype=float)

    if not us10y.empty and not us2y.empty:
        spread_10_2 = us10y.reindex(us2y.index, method="ffill") - us2y
    else:
        spread_10_2 = pd.Series(dtype=float)

    return {
        "미국채_10년":          series_summary(us10y,       "미국채 10년"),
        "미국채_2년":           series_summary(us2y,        "미국채 2년"),
        "장단기금리차(10Y-2Y)": series_summary(spread_10_2, "장단기금리차", unit="pp"),
        "하이일드_스프레드":    series_summary(hy_spread,   "하이일드 스프레드", unit="bp"),
        "달러인덱스":           series_summary(dxy,         "달러인덱스", unit="pt"),
    }


# ──────────────────────────────────────────────
# 4. 반도체 재고 순환 지표
# ──────────────────────────────────────────────
def get_semiconductor_inventory() -> dict:
    fred  = get_fred_client()
    end   = datetime.now()
    start = end - timedelta(days=400)
    result = {}

    try:
        inv = fred.get_series("MNFCTRIRSMSA334S",
                              observation_start=start,
                              observation_end=end).dropna()
        if not inv.empty:
            latest = float(inv.iloc[-1])
            m3     = float(inv.iloc[-4]) if len(inv) >= 4 else float(inv.iloc[0])
            m6     = float(inv.iloc[-7]) if len(inv) >= 7 else float(inv.iloc[0])
            result["미국_전자부품_재고지수"] = {
                "현재값":        round(latest, 1),
                "3개월전":       round(m3, 1),
                "6개월전":       round(m6, 1),
                "3개월_변동(%)": round((latest - m3) / m3 * 100, 2),
                "6개월_변동(%)": round((latest - m6) / m6 * 100, 2),
                "기준월":        str(inv.index[-1])[:7],
                "해석":          "상승=재고 축적(위험), 하락=재고 소진(긍정)",
            }
    except Exception as e:
        result["미국_전자부품_재고지수"] = {"오류": str(e)}

    for name, ticker in [("삼성전자", "005930.KS"), ("SK하이닉스", "000660.KS")]:
        try:
            bs = yf.Ticker(ticker).quarterly_balance_sheet
            if bs is None or bs.empty:
                continue
            inv_row = None
            for lbl in ["Inventory", "inventory"]:
                if lbl in bs.index:
                    inv_row = bs.loc[lbl].dropna()
                    break
            if inv_row is None or inv_row.empty:
                continue
            n    = min(4, len(inv_row))
            vals = [round(float(inv_row.iloc[i]) / 1e8) for i in range(n)]
            qtrs = [str(inv_row.index[i])[:7]           for i in range(n)]
            qoq  = round((vals[0] - vals[1]) / abs(vals[1]) * 100, 1) if n >= 2 and vals[1] else None
            yoy  = round((vals[0] - vals[3]) / abs(vals[3]) * 100, 1) if n >= 4 and vals[3] else None
            result[f"{name}_재고자산"] = {
                "최근분기":   f"{qtrs[0]} → {vals[0]:,}억원",
                "전분기":     f"{qtrs[1]} → {vals[1]:,}억원" if n > 1 else "N/A",
                "전전분기":   f"{qtrs[2]} → {vals[2]:,}억원" if n > 2 else "N/A",
                "QoQ변동(%)": qoq,
                "YoY변동(%)": yoy,
                "해석":       "증가=재고 축적(위험), 감소=재고 소진(긍정)",
            }
        except Exception as e:
            result[f"{name}_재고자산"] = {"오류": str(e)}

    return result


# ──────────────────────────────────────────────
# 5. 필라델피아 반도체 지수 (SOX)
# ──────────────────────────────────────────────
def get_sox_data() -> dict:
    end   = datetime.now()
    start = end - timedelta(days=40)
    try:
        raw = yf.download("^SOX",
                          start=start.strftime("%Y-%m-%d"),
                          end=end.strftime("%Y-%m-%d"),
                          progress=False)
        sox = raw["Close"].squeeze().dropna()
        if sox.empty:
            return {"오류": "SOX 데이터 없음"}
        latest = float(sox.iloc[-1])
        w_ago  = float(sox.iloc[-6]) if len(sox) >= 6 else float(sox.iloc[0])
        m_ago  = float(sox.iloc[0])
        ma5    = float(sox.tail(5).mean())
        ma20   = float(sox.tail(20).mean()) if len(sox) >= 20 else None
        vol20  = float(sox.tail(20).std() / sox.tail(20).mean() * 100) if len(sox) >= 20 else None
        return {
            "현재값":          round(latest, 2),
            "1주_변동":        round(latest - w_ago, 2),
            "1주_변동률(%)":   round((latest - w_ago) / w_ago * 100, 2),
            "1개월_변동":      round(latest - m_ago, 2),
            "1개월_변동률(%)": round((latest - m_ago) / m_ago * 100, 2),
            "MA5":             round(ma5, 2),
            "MA20":            round(ma20, 2) if ma20 else None,
            "MA5_이격도(%)":   round((latest - ma5) / ma5 * 100, 2),
            "20일_변동성(%)":  round(vol20, 2) if vol20 else None,
            "30일_최고":       round(float(sox.max()), 2),
            "30일_최저":       round(float(sox.min()), 2),
            "기준일":          str(sox.index[-1])[:10],
        }
    except Exception as e:
        return {"오류": str(e)}


# ──────────────────────────────────────────────
# 전체 수집 통합
# ──────────────────────────────────────────────
def collect_all_data() -> dict:
    print("📡 데이터 수집 시작...")
    data = {
        "수집일시":             datetime.now().strftime("%Y-%m-%d %H:%M"),
        "earnings_news_prompt": get_earnings_news_prompt(),
    }
    print("  ② 컨센서스 (DART + Yahoo Finance)...")
    data["consensus"] = get_consensus_data()

    print("  ③ 매크로 (FRED + yfinance)...")
    data["macro"] = get_macro_data()

    print("  ④ 반도체 재고 순환...")
    data["semiconductor_inventory"] = get_semiconductor_inventory()

    print("  ⑤ SOX 지수...")
    data["sox"] = get_sox_data()

    print("✅ 수집 완료")
    return data
