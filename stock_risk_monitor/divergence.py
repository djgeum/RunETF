"""
divergence.py
─────────────
선행층. 미국 시장의 약세 다이버전스 3종을 판정합니다.

D1 브레드스   : SPY 신고가인데 RSP/SPY 비율 하락 (소수 대형주만 상승)
D2 AI 리더십  : SPY 신고가인데 SOX/SPY 비율 하락 (반도체가 시장 주도권 상실)
D3 신용       : SPY 신고가인데 하이일드 스프레드 상승 반등 (채권시장 위험 감지)

모든 유형은 60일·120일 이중 확인으로 중간 조정을 걸러냅니다.
"""

import config as C
from signals import Signal, clean, last, asof, slope, is_new_high, pct_n


def _ratio_diverging(numer, denom, win_short, win_long):
    """numer/denom 비율의 단·장기 기울기가 모두 음수인지"""
    n = clean(numer)
    d = clean(denom)
    idx = n.index.intersection(d.index)
    if len(idx) < win_long:
        return False, None
    ratio = (n.loc[idx] / d.loc[idx]).dropna()
    s_short = slope(ratio, win_short)
    s_long  = slope(ratio, win_long)
    if s_short is None or s_long is None:
        return False, None
    return (s_short < 0 and s_long < 0), s_short


def eval_divergence(spy, rsp, sox, hy) -> list:
    out = []
    spy_high = is_new_high(spy, C.DIV_NEWHIGH_WIN)
    spy_asof = asof(spy)

    # ── D1: 브레드스 다이버전스 ──
    div1, sl1 = _ratio_diverging(rsp, spy, C.DIV_SLOPE_WIN, C.DIV_CONFIRM_WIN)
    out.append(Signal(
        "D1", "브레드스 다이버전스",
        bool(spy_high and div1),
        f"SPY신고가={spy_high}, RSP/SPY기울기={sl1:.2e}" if sl1 is not None else "데이터 부족",
        "SPY 60일 신고가인데 등가중이 뒤처짐 (소수 대형주 편중)",
        spy_asof,
    ))

    # ── D2: AI 리더십 다이버전스 ──
    div2, sl2 = _ratio_diverging(sox, spy, C.DIV_SLOPE_WIN, C.DIV_CONFIRM_WIN)
    out.append(Signal(
        "D2", "AI 리더십 다이버전스",
        bool(spy_high and div2),
        f"SPY신고가={spy_high}, SOX/SPY기울기={sl2:.2e}" if sl2 is not None else "데이터 부족",
        "SPY 신고가인데 반도체가 시장을 못 따라감 (AI 주도권 약화)",
        spy_asof,
    ))

    # ── D3: 신용 다이버전스 ──
    hy_s = clean(hy)
    div3 = False
    d3_txt = "데이터 부족"
    if len(hy_s) >= C.DIV_NEWHIGH_WIN:
        low60 = float(hy_s.tail(C.DIV_NEWHIGH_WIN).min())
        cur   = float(hy_s.iloc[-1])
        rebound_abs = cur - low60
        rebound_pct = rebound_abs / low60 if low60 else 0
        hy_slope    = slope(hy_s, C.DIV_SLOPE_WIN)
        cond = (
            spy_high
            and hy_slope is not None and hy_slope > 0
            and rebound_pct >= C.DIV_HY_REBOUND_PCT
            and rebound_abs >= C.DIV_HY_REBOUND_ABS
        )
        div3 = bool(cond)
        d3_txt = f"60일저점 {low60:.2f}→현재 {cur:.2f} (+{rebound_abs*100:.0f}bp, {rebound_pct*100:+.0f}%)"
    out.append(Signal(
        "D3", "신용 다이버전스",
        div3,
        d3_txt,
        "SPY 신고가인데 하이일드가 저점 대비 +15% & +40bp 반등",
        asof(hy),
    ))

    return out
