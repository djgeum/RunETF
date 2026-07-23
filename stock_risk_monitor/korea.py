"""
korea.py
────────
확인층. 관세청 반도체 수출 데이터로 실물 둔화를 판정합니다.

E1 수출단가 = 수출금액 / 수출물량  → DRAM/HBM 가격의 프록시
E2 수출액   = 반도체 수출금액        → 세계 수요의 실시간 프록시

둘 다 계절성 제거를 위해 YoY(전년동월대비)로 판정합니다.
월별 데이터이므로 갱신 여부를 먼저 확인합니다.
"""

import pandas as pd
import config as C
from signals import Signal, clean, consec_slowing


def _yoy(series: pd.Series) -> pd.Series:
    """YYYY-MM 인덱스 월별 계열의 전년동월대비 % (12개월 전 대비)"""
    s = clean(series)
    if len(s) < 13:
        return pd.Series(dtype=float)
    return (s.pct_change(12) * 100).dropna()


def eval_korea(kr_value: pd.Series, kr_weight: pd.Series) -> list:
    out = []

    v = clean(kr_value)
    w = clean(kr_weight)

    # ── E1: 수출 단가 ──
    price_txt, price_fire, price_asof = "데이터 부족", False, "N/A"
    if len(v) and len(w):
        idx = v.index.intersection(w.index)
        if len(idx) >= 13:
            price = (v.loc[idx] / w.loc[idx]).dropna()   # 단위당 단가
            price_yoy = _yoy(price)
            if len(price_yoy):
                cur = float(price_yoy.iloc[-1])
                neg   = cur < C.EXPORT_PRICE_YOY_NEG
                slow  = consec_slowing(price_yoy, C.EXPORT_PRICE_SLOW_M, C.EXPORT_SLOW_MIN_DROP)
                price_fire = bool(neg or slow)
                price_asof = str(price_yoy.index[-1])
                price_txt  = f"단가 YoY {cur:+.1f}% (음수전환={neg}, {C.EXPORT_PRICE_SLOW_M}개월둔화={slow})"
    out.append(Signal(
        "E1", "반도체 수출단가 둔화",
        price_fire, price_txt,
        f"단가 YoY 음수 전환 또는 {C.EXPORT_PRICE_SLOW_M}개월 연속 둔화",
        price_asof,
    ))

    # ── E2: 수출액 ──
    val_txt, val_fire, val_asof = "데이터 부족", False, "N/A"
    val_yoy = _yoy(v)
    if len(val_yoy):
        cur = float(val_yoy.iloc[-1])
        neg  = cur < C.EXPORT_VALUE_YOY_NEG
        slow = consec_slowing(val_yoy, C.EXPORT_VALUE_SLOW_M, C.EXPORT_SLOW_MIN_DROP)
        val_fire = bool(neg or slow)
        val_asof = str(val_yoy.index[-1])
        val_txt  = f"수출액 YoY {cur:+.1f}% (음수전환={neg}, {C.EXPORT_VALUE_SLOW_M}개월둔화={slow})"
    out.append(Signal(
        "E2", "반도체 수출액 둔화",
        val_fire, val_txt,
        f"수출액 YoY 음수 전환 또는 {C.EXPORT_VALUE_SLOW_M}개월 연속 둔화",
        val_asof,
    ))

    return out


def latest_report_month(kr_value: pd.Series) -> str:
    """관세청 데이터의 최신 발표월 (해제 규칙 판정용)"""
    v = clean(kr_value)
    return str(v.index[-1]) if len(v) else ""
