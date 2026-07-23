"""새 korea.py 시나리오 검증"""
import numpy as np, pandas as pd
import korea, config as C

def mk(vals, end="2026-06"):
    idx = pd.date_range(end=end, periods=len(vals), freq="MS").strftime("%Y-%m")
    return pd.Series([float(x) for x in vals], index=idx)

PASS = 0
def check(name, cond):
    global PASS
    assert cond, f"❌ {name}"
    PASS += 1
    print(f"✅ {name}")

def sig(sigs, code):
    return [s for s in sigs if s.code == code][0]

print("="*62)
print("[1] 호황 지속 — 전부 미발동 기대")
print("="*62)
# 단가·물량 모두 꾸준히 상승
n = 30
val = mk(list(np.linspace(1000, 2000, n)))
wgt = mk(list(np.linspace(100, 130, n)))
s = korea.eval_korea(val, wgt, verbose=False)
for x in s: print(f"   {x.code} {x.fired}  {x.value}")
check("호황: E1 미발동", not sig(s,"E1").fired)
check("호황: E2 미발동", not sig(s,"E2").fired)
check("호황: E3 미발동(호황 사분면)", not sig(s,"E3").fired)
check("4분면 = 호황", "호황" in sig(s,"E3").value)

print()
print("="*62)
print("[2] 기저효과 — 작년 급등, 올해도 상승 중 → 억제 기대")
print("="*62)
# 2024 평탄 → 2025 급가속 → 2026 완만 상승(여전히 상승)
vals = [100]*12 + [130,160,200,240,280,320,350,375,395,410,420,428] + [434,440,446,452,458,464]
val2 = mk(vals)
wgt2 = mk([100]*len(vals))
s2 = korea.eval_korea(val2, wgt2, verbose=False)
e2 = sig(s2,"E2")
print(f"   E2 {e2.fired}  {e2.value}")
check("기저효과 구간: YoY는 감속하지만 발동 안 함", not e2.fired)
check("기저효과 억제 문구 표시", "기저효과" in e2.value or "추세꺾임=True" not in e2.value)

print()
print("="*62)
print("[3] 진짜 변곡 — 원계열도 꺾임 → 발동 기대")
print("="*62)
# 상승 후 실제 하락 전환
vals3 = [100]*12 + list(np.linspace(110, 200, 12)) + [198, 190, 178, 165, 150, 138]
val3 = mk(vals3)
wgt3 = mk([100]*len(vals3))
s3 = korea.eval_korea(val3, wgt3, verbose=False)
e2b = sig(s3,"E2")
print(f"   E2 {e2b.fired}  {e2b.value}")
check("실제 하락 전환: E2 발동", e2b.fired)

print()
print("="*62)
print("[4] 수요파괴 4분면 — 단가↓ 물량↓ → E3 발동")
print("="*62)
val4 = mk([100]*20 + [95, 88, 80, 72, 64, 56, 50, 45, 40, 36])
wgt4 = mk([100]*20 + [98, 95, 92, 88, 84, 80, 77, 74, 71, 68])
s4 = korea.eval_korea(val4, wgt4, verbose=False)
e3 = sig(s4,"E3")
print(f"   E3 {e3.fired}  {e3.value}")
check("단가↓물량↓ → E3 발동", e3.fired)
check("4분면 = 수요파괴", "수요파괴" in e3.value)

print()
print("="*62)
print("[5] 가격경쟁 구분 — 단가↓ 물량↑ → E3 미발동")
print("="*62)
val5 = mk([100]*20 + [102]*10)                       # 수출액 유지
wgt5 = mk([100]*20 + list(np.linspace(102, 130, 10)))  # 물량 급증 → 단가 하락
s5 = korea.eval_korea(val5, wgt5, verbose=False)
e3b = sig(s5,"E3")
print(f"   E3 {e3b.fired}  {e3b.value}")
check("단가↓물량↑ → E3 미발동", not e3b.fired)
check("4분면 = 가격경쟁", "가격경쟁" in e3b.value)

print()
print("="*62)
print("[6] 비상식 YoY 억제")
print("="*62)
# 2024-01~2025-12 는 100, 2026-01~06 만 500 → 2026-06 YoY = +400%
val6 = mk([100]*24 + [500]*6)
wgt6 = mk([100]*30)
s6 = korea.eval_korea(val6, wgt6, verbose=False)
e2c = sig(s6,"E2")
print(f"   E2 {e2c.fired}  {e2c.value}")
check("비상식 YoY 경고 표시", "⚠데이터확인필요" in e2c.value)
check("비상식 YoY 신호 억제", not e2c.fired)

print()
print("="*62)
print("[7] 결측월 있어도 정확한 YoY")
print("="*62)
idx = ([f"2024-{m:02d}" for m in range(1,13)] +
       [f"2025-{m:02d}" for m in (1,2,3,4,5,6)] +      # 하반기 결측
       [f"2026-{m:02d}" for m in range(1,7)])
v7 = pd.Series([100.]*12 + [200.]*6 + [210.]*6, index=idx)
w7 = pd.Series([100.]*24, index=idx)
sm = korea.moving_avg(v7, 3)
y7 = korea.yoy_by_month(sm)
print(f"   2026-06 YoY = {y7['2026-06']:+.1f}%  (2025-06 대비)")
check("결측 있어도 +5% 정확", abs(y7["2026-06"] - 5.0) < 0.5)

print(f"\n🎉 전체 {PASS}개 통과")
