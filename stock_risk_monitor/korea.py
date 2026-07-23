"""
korea.py
────────
확인층. 관세청 반도체 수출 데이터로 실물 둔화(변곡점)를 판정합니다.

목적은 '지금 얼마나 좋은가(Level)'가 아니라 '언제 방향이 바뀌는가(Inflection)'입니다.

  E1 수출단가(ASP) 둔화  : DRAM/HBM 가격 프록시
  E2 수출액 둔화         : 세계 메모리 수요 프록시
  E3 수요파괴            : ASP와 물량이 동시 하락 (가장 위험한 조합)

핵심 설계
  · YoY는 위치가 아닌 '월 키' 명시 매칭 (결측월이 있어도 정확)
  · 3개월 이동평균 적용 후 YoY 계산 (단월 노이즈 제거)
  · 기저효과 방어: YoY 감속만으로는 발동하지 않고 원계열 추세도 꺾여야 발동
  · 상식 범위(±100%) 벗어나면 데이터 이상으로 보고 신호 억제
"""

import numpy as np
import pandas as pd

import config as C
from signals import Signal, clean, consec_slowing


# ══════════════════════════════════════════════
# 시계열 유틸 (월별 YYYY-MM 인덱스 전용)
# ══════════════════════════════════════════════
def _prev_year_key(ym: str) -> str:
    """'2026-06' → '2025-06'"""
    try:
        y, m = str(ym).split("-")
        return f"{int(y)-1}-{m}"
    except Exception:
        return ""


def yoy_by_month(series: pd.Series) -> pd.Series:
    """
    전년 동월 대비 % 변화.
    월 키를 명시 매칭하므로 중간에 결측월이 있어도 잘못된 쌍을 비교하지 않습니다.
    """
    s = clean(series)
    if len(s) < 2:
        return pd.Series(dtype=float)
    out = {}
    for ym in s.index:
        prev = _prev_year_key(ym)
        if prev in s.index:
            base = float(s.loc[prev])
            if base != 0:
                out[str(ym)] = (float(s.loc[ym]) - base) / abs(base) * 100.0
    return pd.Series(out).sort_index()


def moving_avg(series: pd.Series, window: int) -> pd.Series:
    """단순 이동평균. 결측월이 있으면 그대로 두고 관측치 기준으로 계산."""
    s = clean(series)
    if len(s) < window:
        return pd.Series(dtype=float)
    return s.rolling(window).mean().dropna()


def slope(series: pd.Series, n: int):
    """최근 n개 구간의 선형회귀 기울기 (값/개월)"""
    s = clean(series)
    if len(s) < n or n < 2:
        return None
    y = s.tail(n).to_numpy(dtype=float)
    x = np.arange(len(y))
    try:
        return float(np.polyfit(x, y, 1)[0])
    except Exception:
        return None


def _num(x):
    """크기에 따라 자릿수를 조절해 -0.0 같은 표기를 피함"""
    if x is None:
        return "N/A"
    a = abs(x)
    if a >= 1000:
        return f"{x:+,.0f}"
    if a >= 10:
        return f"{x:+,.1f}"
    if a >= 0.1:
        return f"{x:+.2f}"
    return f"{x:+.4f}"


def _fmt(s: pd.Series, n=6, unit="", scale=1.0):
    s = clean(s)
    if not len(s):
        return "없음"
    return " | ".join(f"{i}:{v/scale:,.1f}{unit}" for i, v in s.tail(n).items())


# ══════════════════════════════════════════════
# 개별 지표 평가 헬퍼
# ══════════════════════════════════════════════
def _eval_series(raw: pd.Series, label: str, unit: str, verbose: bool):
    """
    하나의 계열(단가 또는 수출액)에 대해 발동 여부와 설명을 계산.
    반환: (fired, text, asof, detail_dict)
    """
    d = {"yoy_cur": None, "slope": None, "smoothed": pd.Series(dtype=float)}
    s = clean(raw)
    if len(s) < 2:
        return False, "데이터 부족", "N/A", d

    # ① 3개월 이동평균으로 단월 노이즈 제거
    sm = moving_avg(s, C.EXPORT_MA_WINDOW)
    d["smoothed"] = sm
    if len(sm) < 2:
        return False, "데이터 부족(평활 후)", "N/A", d

    # ② 평활 계열의 YoY (월 키 매칭)
    yoy = yoy_by_month(sm)
    if not len(yoy):
        return False, "전년 동월 데이터 없음", "N/A", d

    cur  = float(yoy.iloc[-1])
    asof = str(yoy.index[-1])
    d["yoy_cur"] = cur

    # ③ 상식 범위 밖이면 데이터 이상 → 신호 억제
    if abs(cur) > C.YOY_SANITY_LIMIT:
        txt = (f"{label} YoY {cur:+.1f}% ⚠데이터확인필요 "
               f"(±{C.YOY_SANITY_LIMIT:.0f}% 초과, 신호 억제)")
        return False, txt, asof, d

    # ④ 조건 A: YoY 음수 전환 (확인 지표)
    neg = cur < 0.0

    # ⑤ 조건 B: YoY 2개월 연속 감속 (선행 지표)
    decel = consec_slowing(yoy, C.EXPORT_PRICE_SLOW_M, C.EXPORT_SLOW_MIN_DROP)

    # ⑥ 기저효과 방어: 원계열(3MMA) 기울기가 실제로 꺾였는지 확인
    lv_slope = slope(sm, C.EXPORT_SLOPE_WIN)
    d["slope"] = lv_slope
    level_down = (lv_slope is not None and lv_slope <= 0)

    if C.REQUIRE_LEVEL_CONFIRM:
        decel_fire = bool(decel and level_down)
        guard = "" if (not decel or level_down) else " [기저효과로 판단, 억제]"
    else:
        decel_fire = bool(decel)
        guard = ""

    fired = bool(neg or decel_fire)

    slope_txt = "N/A" if lv_slope is None else f"{_num(lv_slope)}{unit}/월"
    txt = (f"{label} YoY {cur:+.1f}% | 추세 {slope_txt} "
           f"(음수={neg}, 감속={decel}, 추세꺾임={level_down}){guard}")

    if verbose:
        print(f"    [{label}] YoY 최근: {_fmt(yoy, unit='%')}")

    return fired, txt, asof, d


# ══════════════════════════════════════════════
# 메인 평가
# ══════════════════════════════════════════════
def eval_korea(kr_value: pd.Series, kr_weight: pd.Series, verbose: bool = True) -> list:
    out = []
    v = clean(kr_value)
    w = clean(kr_weight)

    # ── 데이터 품질 진단 로그 ──
    if verbose and len(v):
        print(f"    [수출액] 최근: {_fmt(v, unit='M$', scale=1e6)}")
        print(f"    [보유월] {len(v)}개월 ({v.index[0]} ~ {v.index[-1]})")
        try:
            exp = pd.period_range(v.index[0], v.index[-1], freq="M").strftime("%Y-%m")
            miss = [m for m in exp if m not in v.index]
            if miss:
                print(f"    ! 결측월 {len(miss)}개: {','.join(miss[:12])}"
                      f"{' ...' if len(miss) > 12 else ''}")
            else:
                print(f"    ✓ 결측월 없음")
        except Exception:
            pass

    # ══════════════════════════════════════════
    # 단가 계열 준비 (수출액 ÷ 물량)
    # ══════════════════════════════════════════
    price = pd.Series(dtype=float)
    if len(v) and len(w):
        idx = v.index.intersection(w.index)
        if len(idx):
            price = (v.loc[idx] / w.loc[idx]).replace([np.inf, -np.inf], np.nan).dropna()
            if verbose and len(price):
                print(f"    [단가] 최근: {_fmt(price, unit='$/kg')}")

    # ══════════════════════════════════════════
    # E1 · 수출단가(ASP) 둔화
    # ══════════════════════════════════════════
    p_fired, p_txt, p_asof, p_d = _eval_series(price, "단가", "$/kg", verbose)
    out.append(Signal(
        "E1", "반도체 수출단가 둔화", p_fired, p_txt,
        f"3MMA YoY 음수 전환 또는 "
        f"{C.EXPORT_PRICE_SLOW_M}개월 연속 감속(스텝 {C.EXPORT_SLOW_MIN_DROP}%p 이상)"
        + (" + 원계열 추세 꺾임" if C.REQUIRE_LEVEL_CONFIRM else ""),
        p_asof,
    ))

    # ══════════════════════════════════════════
    # E2 · 수출액 둔화
    # ══════════════════════════════════════════
    v_fired, v_txt, v_asof, v_d = _eval_series(v, "수출액", "$", verbose)
    out.append(Signal(
        "E2", "반도체 수출액 둔화", v_fired, v_txt,
        f"3MMA YoY 음수 전환 또는 "
        f"{C.EXPORT_VALUE_SLOW_M}개월 연속 감속(스텝 {C.EXPORT_SLOW_MIN_DROP}%p 이상)"
        + (" + 원계열 추세 꺾임" if C.REQUIRE_LEVEL_CONFIRM else ""),
        v_asof,
    ))

    # ══════════════════════════════════════════
    # E3 · 수요파괴 (ASP × 물량 4분면)
    #      수출액 = 단가 × 물량 이므로 독립 정보는 '단가와 물량'
    # ══════════════════════════════════════════
    if C.DEMAND_DESTRUCTION_ON:
        q_fired, q_txt, q_asof = _eval_quadrant(price, w, verbose)
        out.append(Signal(
            "E3", "수요파괴 (단가↓ 물량↓)", q_fired, q_txt,
            "단가와 물량의 3MMA 기울기가 동시에 음수",
            q_asof,
        ))

    return out


def _eval_quadrant(price: pd.Series, weight: pd.Series, verbose: bool):
    """
    ASP × 물량 4분면 판정.
      단가↓ 물량↓ = 수요 파괴      ← 가장 위험 (발동)
      단가↓ 물량↑ = 가격경쟁/점유율 확대
      단가↑ 물량↓ = 공급제약/믹스개선
      단가↑ 물량↑ = 호황
    """
    p_sm = moving_avg(price,  C.EXPORT_MA_WINDOW)
    w_sm = moving_avg(weight, C.EXPORT_MA_WINDOW)
    if len(p_sm) < C.EXPORT_SLOPE_WIN or len(w_sm) < C.EXPORT_SLOPE_WIN:
        return False, "데이터 부족", "N/A"

    p_s = slope(p_sm, C.EXPORT_SLOPE_WIN)
    w_s = slope(w_sm, C.EXPORT_SLOPE_WIN)
    if p_s is None or w_s is None:
        return False, "기울기 계산 불가", "N/A"

    p_dn, w_dn = p_s < 0, w_s < 0
    if p_dn and w_dn:
        quad, fired = "수요파괴 (단가↓ 물량↓)", True
    elif p_dn and not w_dn:
        quad, fired = "가격경쟁 (단가↓ 물량↑)", False
    elif not p_dn and w_dn:
        quad, fired = "공급제약 (단가↑ 물량↓)", False
    else:
        quad, fired = "호황 (단가↑ 물량↑)", False

    asof = str(p_sm.index[-1])
    txt  = f"{quad} | 단가 {_num(p_s)}$/kg·월, 물량 {_num(w_s/1000)}톤·월"
    if verbose:
        print(f"    [4분면] {quad}")
    return fired, txt, asof


def latest_report_month(kr_value: pd.Series) -> str:
    """관세청 데이터의 최신 발표월 (해제 규칙 판정용)"""
    v = clean(kr_value)
    return str(v.index[-1]) if len(v) else ""
