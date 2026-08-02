"""
valuation.py
────────────
KOSPI 동적 밸류에이션 밴드 계산.

설계 (사용자 확정):
  중심선 = 조정 PBR = 역사적 평균 PBR × (1 + k × 영업이익성장률)
  밴드폭 = 역사적 10년 PBR 표준편차 σ
  상단   = 중심선 + 2σ   → 이격율 +100%
  하단   = 중심선 − 2σ   → 이격율 −100%
  이격율 = (현재 PBR − 중심선) / (2σ) × 100

특징
  · pykrx 로그인 실패(90일 비번 만료 등)해도 리포트 전체는 죽지 않음
  · 로그인/조회 실패 시 별도 플래그로 '비밀번호 갱신 필요' 알림 유도
  · 성장률은 지수 EPS(종가/PER) 역산. 상식범위 밖이면 0 처리.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import config as C


# ══════════════════════════════════════════════
# 결과 자료구조
# ══════════════════════════════════════════════
@dataclass
class Valuation:
    ok:            bool  = False   # 계산 성공 여부
    login_failed:  bool  = False   # 로그인/인증 실패 (비번 갱신 알림용)
    note:          str   = ""      # 실패 사유

    index_now:     float = None    # 현재 지수
    pbr_now:       float = None    # 현재 PBR
    pbr_mean:      float = None    # 역사적 평균 PBR
    pbr_sigma:     float = None    # 역사적 표준편차
    growth:        float = None    # 반영된 성장률(%)
    pbr_center:    float = None    # 조정 PBR (중심선)
    pbr_upper:     float = None    # 상단 PBR
    pbr_lower:     float = None    # 하단 PBR
    index_center:  float = None    # 적정 지수 (중심)
    index_upper:   float = None
    index_lower:   float = None
    dispersion:    float = None    # 이격율(%)
    label:         str   = ""      # 상태 라벨
    years:         int   = 0       # 실제 사용 연수
    asof:          str   = ""      # 기준일


# ══════════════════════════════════════════════
# KRX 로그인 (환경변수 매핑 + 실패 감지)
# ══════════════════════════════════════════════
def _prepare_krx_login() -> bool:
    """
    GitHub Secret(KRX_USER_ID/PW)을 pykrx가 읽는 KRX_ID/KRX_PW로 매핑.
    자격증명이 없으면 False.
    """
    uid = os.environ.get(C.KRX_ID_ENV, "") or os.environ.get("KRX_ID", "")
    upw = os.environ.get(C.KRX_PW_ENV, "") or os.environ.get("KRX_PW", "")
    if not uid or not upw:
        return False
    os.environ["KRX_ID"] = uid
    os.environ["KRX_PW"] = upw
    return True


# ══════════════════════════════════════════════
# 상태 라벨
# ══════════════════════════════════════════════
def _label_for(dispersion: float) -> str:
    for threshold, name in C.VAL_BAND_LABELS:
        if dispersion >= threshold:
            return name
    return "하단 이탈 (저평가)"


# ══════════════════════════════════════════════
# 성장률 (지수 EPS 역산)
# ══════════════════════════════════════════════
def _estimate_growth(fund_df) -> float:
    """
    지수 EPS = 종가 / PER.
    1년 전 대비 EPS 성장률(%)을 반환. 상식범위 밖이면 0.
    """
    if C.GROWTH_SOURCE == "off":
        return 0.0
    try:
        df = fund_df.dropna(subset=["종가", "PER"])
        df = df[df["PER"] > 0]
        if len(df) < 2:
            return 0.0
        df = df.copy()
        df["EPS"] = df["종가"] / df["PER"]

        latest_date = df.index[-1]
        target_date = latest_date - timedelta(days=365)
        # 1년 전 시점에 가장 가까운 행
        past = df[df.index <= target_date]
        if len(past) == 0:
            return 0.0
        eps_now  = float(df["EPS"].iloc[-1])
        eps_past = float(past["EPS"].iloc[-1])
        if eps_past <= 0:
            return 0.0
        g = (eps_now - eps_past) / eps_past * 100.0
        if abs(g) > C.GROWTH_SANITY_LIMIT:
            print(f"    ! 성장률 {g:+.1f}% 상식범위 초과 → 0 처리")
            return 0.0
        return g
    except Exception as e:
        print(f"    ! 성장률 계산 실패: {e}")
        return 0.0


# ══════════════════════════════════════════════
# 메인 계산
# ══════════════════════════════════════════════
def calculate(verbose: bool = True) -> Valuation:
    v = Valuation()

    # ── 자격증명 확인 ──
    if not _prepare_krx_login():
        v.note = "KRX 계정 미설정 (KRX_USER_ID/PW)"
        if verbose:
            print(f"    x {v.note}")
        return v

    # ── pykrx import (실패해도 전체는 진행) ──
    try:
        from pykrx import stock
    except Exception as e:
        v.note = f"pykrx import 실패: {e}"
        if verbose:
            print(f"    x {v.note}")
        return v

    end   = datetime.now()
    start = end - timedelta(days=int(C.PBR_HISTORY_YEARS * 365.25) + 10)
    s_str = start.strftime("%Y%m%d")
    e_str = end.strftime("%Y%m%d")

    # ── 데이터 조회 ──
    try:
        fund = stock.get_index_fundamental_by_date(s_str, e_str, C.KOSPI_INDEX_CODE)
    except Exception as e:
        msg = str(e).lower()
        # 로그인/인증 관련 키워드면 비번 만료 가능성 → 별도 플래그
        if any(k in msg for k in ("login", "로그인", "auth", "인증", "unauthorized", "password", "비밀번호")):
            v.login_failed = True
            v.note = f"KRX 로그인/인증 실패 (비밀번호 갱신 필요 가능): {e}"
        else:
            v.note = f"KRX 조회 실패: {e}"
        if verbose:
            print(f"    x {v.note}")
        return v

    # ── 데이터 유효성 ──
    if fund is None or len(fund) == 0:
        # 로그인은 됐지만 빈 데이터 = 회원제 차단 또는 세션 만료 의심
        v.login_failed = True
        v.note = "KRX 응답이 비어 있음 (세션 만료/차단 의심 → 비밀번호 확인)"
        if verbose:
            print(f"    x {v.note}")
        return v

    if "PBR" not in fund.columns or "종가" not in fund.columns:
        v.note = f"필요 컬럼 없음 (수신 컬럼: {list(fund.columns)})"
        if verbose:
            print(f"    x {v.note}")
        return v

    # ── 역사적 통계 ──
    pbr_series = fund["PBR"].dropna()
    pbr_series = pbr_series[pbr_series > 0]
    if len(pbr_series) < 250:   # 최소 1년치
        v.note = f"PBR 데이터 부족 ({len(pbr_series)}일)"
        if verbose:
            print(f"    x {v.note}")
        return v

    pbr_mean  = float(pbr_series.mean())
    pbr_sigma = float(pbr_series.std())
    pbr_now   = float(pbr_series.iloc[-1])
    index_now = float(fund["종가"].dropna().iloc[-1])
    years     = round(len(pbr_series) / 252, 1)

    # ── 성장률 & 조정 PBR (중심선) ──
    growth     = _estimate_growth(fund)
    pbr_center = pbr_mean * (1 + C.PBR_GROWTH_K * growth / 100.0)

    # ── 밴드 (±2σ) ──
    band       = C.PBR_BAND_SIGMA * pbr_sigma
    pbr_upper  = pbr_center + band
    pbr_lower  = pbr_center - band

    # ── Index BPS 역산 → 적정 지수 3선 ──
    # BPS = 현재지수 / 현재PBR
    index_bps    = index_now / pbr_now if pbr_now else None
    index_center = index_bps * pbr_center if index_bps else None
    index_upper  = index_bps * pbr_upper  if index_bps else None
    index_lower  = index_bps * pbr_lower  if index_bps else None

    # ── 이격율 (±2σ를 ±100%에 매핑) ──
    dispersion = (pbr_now - pbr_center) / band * 100.0 if band else 0.0
    label      = _label_for(dispersion)

    # ── 결과 채우기 ──
    v.ok          = True
    v.index_now   = round(index_now, 2)
    v.pbr_now     = round(pbr_now, 3)
    v.pbr_mean    = round(pbr_mean, 3)
    v.pbr_sigma   = round(pbr_sigma, 3)
    v.growth      = round(growth, 1)
    v.pbr_center  = round(pbr_center, 3)
    v.pbr_upper   = round(pbr_upper, 3)
    v.pbr_lower   = round(pbr_lower, 3)
    v.index_center = round(index_center, 1) if index_center else None
    v.index_upper  = round(index_upper, 1)  if index_upper  else None
    v.index_lower  = round(index_lower, 1)  if index_lower  else None
    v.dispersion  = round(dispersion, 1)
    v.label       = label
    v.years       = years
    v.asof        = str(pbr_series.index[-1])[:10]

    if verbose:
        print(f"    ✓ KOSPI {index_now:,.0f} | PBR {pbr_now:.2f} "
              f"(평균 {pbr_mean:.2f}±{pbr_sigma:.2f}, {years}년)")
        print(f"      중심 {pbr_center:.2f} | 성장률 {growth:+.1f}% | 이격율 {dispersion:+.0f}% [{label}]")

    return v
