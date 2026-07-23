"""
macro.py
────────
동행층. 하이일드·달러·미국채의 스트레스를 판정합니다.
절대수준은 '신규 돌파(전이)'로만 발동하여 경보 피로를 방지합니다.
"""

import config as C
from signals import (Signal, clean, last, asof, diff_n, pct_n, ma,
                     newly_crossed_above)


def eval_macro(hy, dxy, us10y) -> list:
    out = []

    # ── 하이일드: 20일 +50bp AND 상대 +15% ──
    d20 = diff_n(hy, 20)
    p20 = pct_n(hy, 20)
    hy_fire = (d20 is not None and d20 >= C.HY_SURGE_20D and
               p20 is not None and p20 >= C.HY_SURGE_REL_PCT * 100)
    out.append(Signal(
        "HY-20D", "하이일드 급등",
        bool(hy_fire),
        f"20일 {d20*100:+.0f}bp ({p20:+.1f}%)" if d20 is not None and p20 is not None else "N/A",
        f"20일 +{C.HY_SURGE_20D*100:.0f}bp 이면서 상대 +{C.HY_SURGE_REL_PCT*100:.0f}%",
        asof(hy),
    ))
    # 하이일드 신규 4.5% 돌파
    out.append(Signal(
        "HY-CROSS", "하이일드 4.5% 신규돌파",
        newly_crossed_above(hy, C.HY_LEVEL_WARNING, C.CROSS_LOOKBACK),
        f"현재 {last(hy):.2f}%" if last(hy) is not None else "N/A",
        f"{C.HY_LEVEL_WARNING}% 선을 최근 {C.CROSS_LOOKBACK}일 내 신규 돌파",
        asof(hy),
    ))

    # ── 달러인덱스: 20일 +3% OR 105 신규돌파 ──
    dxy_p20 = pct_n(dxy, 20)
    dxy_fire = (dxy_p20 is not None and dxy_p20 >= C.DXY_SURGE_20D_PCT) or \
               newly_crossed_above(dxy, C.DXY_LEVEL_WARNING, C.CROSS_LOOKBACK)
    out.append(Signal(
        "DXY-20D", "달러 급등",
        bool(dxy_fire),
        f"20일 {dxy_p20:+.2f}% / 현재 {last(dxy):.2f}pt" if dxy_p20 is not None else "N/A",
        f"20일 +{C.DXY_SURGE_20D_PCT}% 또는 {C.DXY_LEVEL_WARNING}pt 신규돌파",
        asof(dxy),
    ))

    # ── 미국채 10Y: 급등/급락 각각 ──
    u_d20 = diff_n(us10y, 20)
    u_ma  = ma(us10y, C.US10Y_MA)
    u_cur = last(us10y)

    surge = (u_d20 is not None and u_d20 >= C.US10Y_SURGE_20D and
             u_ma is not None and u_cur is not None and u_cur > u_ma)
    out.append(Signal(
        "UST-SURGE", "미국채 금리급등",
        bool(surge),
        f"20일 {u_d20*100:+.0f}bp / 현재 {u_cur:.2f}%" if u_d20 is not None and u_cur is not None else "N/A",
        f"20일 +{C.US10Y_SURGE_20D*100:.0f}bp 이면서 MA50 상단",
        asof(us10y),
    ))

    plunge = (u_d20 is not None and u_d20 <= C.US10Y_PLUNGE_20D and
              u_ma is not None and u_cur is not None and u_cur < u_ma)
    out.append(Signal(
        "UST-PLUNGE", "미국채 금리급락",
        bool(plunge),
        f"20일 {u_d20*100:+.0f}bp / 현재 {u_cur:.2f}%" if u_d20 is not None and u_cur is not None else "N/A",
        f"20일 {C.US10Y_PLUNGE_20D*100:.0f}bp 이면서 MA50 하단 (침체 공포)",
        asof(us10y),
    ))

    return out
