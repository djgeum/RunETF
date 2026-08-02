"""
diagnose_growth.py
──────────────────
KOSPI EPS 성장률이 '진짜 이익 성장'인지 '주가 상승 착시'인지 진단.

핵심 비교:
  · EPS 증가율 (종가/PER 역산)
  · 지수 증가율
  두 값이 비슷하면 → PER 불변 → 착시 (주가만 오름)
  EPS 증가율 > 지수 증가율 → 실적이 주가보다 빨리 늚 → 진짜 성장
"""
import os
from datetime import datetime, timedelta

uid = os.environ.get("KRX_USER_ID", "") or os.environ.get("KRX_ID", "")
upw = os.environ.get("KRX_USER_PW", "") or os.environ.get("KRX_PW", "")
if not uid or not upw:
    print("❌ KRX 계정 없음"); raise SystemExit(0)
os.environ["KRX_ID"] = uid
os.environ["KRX_PW"] = upw

from pykrx import stock
from pykrx.website.comm import auth
auth.login_krx(uid, upw)

end = datetime.now()
start = end - timedelta(days=800)
df = stock.get_index_fundamental_by_date(
    start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), "1001")

df = df.dropna(subset=["종가", "PER", "PBR"])
df = df[df["PER"] > 0].copy()
df["EPS"] = df["종가"] / df["PER"]
df["BPS"] = df["종가"] / df["PBR"]

now = df.iloc[-1]
target = now.name - timedelta(days=365)
past_rows = df[df.index <= target]
if len(past_rows) == 0:
    print("❌ 1년 전 데이터 없음"); raise SystemExit(0)
past = past_rows.iloc[-1]

def pct(a, b): return (a - b) / b * 100

print("=" * 60)
print("EPS 성장률 = 진짜 이익 성장 vs 주가 상승 착시 진단")
print("=" * 60)
print(f"\n[1년 전] {past.name.date()}")
print(f"  지수 {past['종가']:>8,.0f} | PER {past['PER']:>6.2f} | "
      f"PBR {past['PBR']:>5.2f} | EPS {past['EPS']:>6.1f} | BPS {past['BPS']:>7.1f}")
print(f"\n[현재]   {now.name.date()}")
print(f"  지수 {now['종가']:>8,.0f} | PER {now['PER']:>6.2f} | "
      f"PBR {now['PBR']:>5.2f} | EPS {now['EPS']:>6.1f} | BPS {now['BPS']:>7.1f}")

idx_g = pct(now['종가'], past['종가'])
eps_g = pct(now['EPS'], past['EPS'])
bps_g = pct(now['BPS'], past['BPS'])
per_g = pct(now['PER'], past['PER'])

print("\n" + "=" * 60)
print("증가율 비교")
print("=" * 60)
print(f"  지수 증가율 : {idx_g:+6.1f}%")
print(f"  EPS 증가율  : {eps_g:+6.1f}%   ← 성장률로 쓰이는 값")
print(f"  BPS 증가율  : {bps_g:+6.1f}%   ← 실제 자산 성장 (PBR 기반)")
print(f"  PER 증가율  : {per_g:+6.1f}%")

print("\n" + "=" * 60)
print("판정")
print("=" * 60)
gap = abs(eps_g - idx_g)
if gap < 10:
    print(f"  ⚠️ EPS증가율({eps_g:+.0f}%) ≈ 지수증가율({idx_g:+.0f}%)")
    print("     → PER가 거의 안 변함 = 주가 상승 착시 가능성 높음")
    print("     → EPS 역산 성장률은 신뢰도 낮음. BPS 성장률 사용 권장")
else:
    print(f"  ✓ EPS증가율({eps_g:+.0f}%) ≠ 지수증가율({idx_g:+.0f}%), 차이 {gap:.0f}%p")
    print("     → 실적과 주가가 다르게 움직임 = EPS 성장에 실질 정보 있음")

print(f"\n  참고: BPS(순자산) 증가율 {bps_g:+.1f}% 는 PBR 기반이라")
print(f"        주가 착시가 적음. 성장률 대안으로 고려 가능.")
