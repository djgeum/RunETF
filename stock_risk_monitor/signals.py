"""
signals.py
──────────
공통 신호 자료구조와 시계열 유틸. 판정 모듈들이 공유합니다.
네트워크 접근 없음 → 단위 테스트 가능.
"""

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class Signal:
    code:   str      # 예: "D1", "HY-20D"
    name:   str      # 사람이 읽는 이름
    fired:  bool     # 발동 여부
    value:  str      # 현재 관측값 텍스트
    detail: str      # 조건 설명
    asof:   str = "" # 기준일


# ── 시계열 유틸 ──
def clean(s) -> pd.Series:
    if s is None:
        return pd.Series(dtype=float)
    return pd.Series(s).dropna().astype(float)


def last(s):
    s = clean(s)
    return float(s.iloc[-1]) if len(s) else None


def asof(s) -> str:
    s = clean(s)
    return str(s.index[-1])[:10] if len(s) else "N/A"


def diff_n(s, n):
    s = clean(s)
    if len(s) < n + 1:
        return None
    return float(s.iloc[-1]) - float(s.iloc[-1 - n])


def pct_n(s, n):
    s = clean(s)
    if len(s) < n + 1:
        return None
    base = float(s.iloc[-1 - n])
    if base == 0:
        return None
    return (float(s.iloc[-1]) - base) / base * 100.0


def ma(s, n):
    s = clean(s)
    if len(s) < n:
        return None
    return float(s.tail(n).mean())


def slope(s, n):
    """최근 n개 구간의 선형회귀 기울기 (단위: 값/일)"""
    s = clean(s)
    if len(s) < n:
        return None
    y = s.tail(n).to_numpy()
    x = np.arange(len(y))
    try:
        return float(np.polyfit(x, y, 1)[0])
    except Exception:
        return None


def is_new_high(s, win):
    """현재값이 최근 win 구간의 최고가인지"""
    s = clean(s)
    if len(s) < win:
        return False
    return float(s.iloc[-1]) >= float(s.tail(win).max())


def newly_crossed_above(s, level, lookback):
    """현재는 level 이상이지만 lookback일 전에는 미만이었는지 (신규 돌파)"""
    s = clean(s)
    if len(s) < lookback + 1:
        return False
    cur  = float(s.iloc[-1])
    past = float(s.iloc[-1 - lookback])
    return cur >= level and past < level


def consec_slowing(s, months, min_drop=0.0):
    """
    YoY 계열이 최근 months회 연속 둔화(감소)했는지.
    min_drop: 각 스텝의 최소 하락폭(같은 단위). 노이즈성 미세 하락 제외용.
    """
    s = clean(s)
    if len(s) < months + 1:
        return False
    tail = s.tail(months + 1).tolist()
    return all((tail[i] - tail[i + 1]) >= min_drop for i in range(len(tail) - 1))
