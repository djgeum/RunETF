"""오프라인 판정 검증 (네트워크 불필요)"""
import numpy as np, pandas as pd
import divergence, macro, korea, judge as J, state as S

def mk(v, n=300):
    return pd.Series([v[0]]*(n-len(v)) + list(v))

def mk_dates(vals):
    """월별 YYYY-MM 인덱스 계열"""
    idx = pd.date_range(end="2026-06-01", periods=len(vals), freq="MS").strftime("%Y-%m")
    return pd.Series(vals, index=idx)

PASS = 0
def check(name, cond):
    global PASS
    assert cond, f"❌ {name}"
    PASS += 1
    print(f"✅ {name}")

print("="*58)
print("[A] 다이버전스")
print("="*58)
# 정상 강세장: SPY 신고가 + RSP도 같이 상승 → 다이버전스 없음
n=300
spy_up  = mk(list(np.linspace(400, 520, 130)), n)
rsp_up  = mk(list(np.linspace(150, 200, 130)), n)   # 함께 상승
sox_up  = mk(list(np.linspace(4000, 5200, 130)), n)
hy_flat = mk([3.0]*130, n)
d = divergence.eval_divergence(spy_up, rsp_up, sox_up, hy_flat)
check("강세장 정상 → D1 미발동", not d[0].fired)

# 브레드스 다이버전스: SPY 신고가인데 RSP는 하락
spy_high = mk(list(np.linspace(480, 520, 130)), n)          # 신고가 경신
rsp_down = mk(list(np.linspace(200, 180, 130)), n)          # 하락
d2 = divergence.eval_divergence(spy_high, rsp_down, sox_up, hy_flat)
check("SPY신고가+RSP하락 → D1 발동", d2[0].fired)

# AI 리더십: SPY 신고가인데 SOX 하락
sox_down = mk(list(np.linspace(5200, 4600, 130)), n)
d3 = divergence.eval_divergence(spy_high, rsp_up, sox_down, hy_flat)
check("SPY신고가+SOX하락 → D2 발동", d3[1].fired)

# 신용: SPY 신고가인데 하이일드 저점 대비 +15% & +40bp 반등
hy_rebound = mk(list(np.linspace(3.0, 3.0, 60)) + list(np.linspace(3.0, 3.6, 70)), n)
d4 = divergence.eval_divergence(spy_high, rsp_up, sox_up, hy_rebound)
check("SPY신고가+하이일드반등 → D3 발동", d4[2].fired)

print("="*58)
print("[B] 매크로")
print("="*58)
# 평온
m = macro.eval_macro(mk([3.0]*100,n), mk([100.0]*100,n), mk([4.0]*100,n))
check("평온 → 매크로 전부 미발동", not any(s.fired for s in m))

# 하이일드 20일 +60bp & 상대 +18%
hy_surge = mk(list(np.linspace(3.3, 3.9, 21)), n)
m2 = macro.eval_macro(hy_surge, mk([100.0]*100,n), mk([4.0]*100,n))
check("하이일드 +60bp → HY-20D 발동", m2[0].fired)

# 달러 20일 +4%
dxy_surge = mk(list(np.linspace(100, 104, 21)), n)
m3 = macro.eval_macro(mk([3.0]*100,n), dxy_surge, mk([4.0]*100,n))
check("달러 +4% → DXY-20D 발동", m3[2].fired)

# 국채 급등 +35bp & MA50 상단
us_surge = mk([4.0]*60 + list(np.linspace(4.0, 4.35, 21)), n)
m4 = macro.eval_macro(mk([3.0]*100,n), mk([100.0]*100,n), us_surge)
check("국채 +35bp → UST-SURGE 발동", m4[3].fired)

print("="*58)
print("[C] 한국 수출 (확인층)")
print("="*58)
# 단가 상승 지속 → 미발동
val_up = mk_dates(list(np.linspace(80, 120, 26)))    # 수출액 증가
wgt_fl = mk_dates([10.0]*26)                           # 물량 일정 → 단가 상승
k = korea.eval_korea(val_up, wgt_fl)
check("수출단가 상승 → E1 미발동", not k[0].fired)

# 단가 YoY 음수: 전년보다 단가가 크게 하락 (물량 급증)
# 앞 13개월은 단가 10, 최근 13개월은 단가 7로 급락 → YoY 뚜렷한 음수
val_c = mk_dates([100.0]*26)
wgt_c = mk_dates([10.0]*20 + [14.3]*6)   # 최근 6개월 물량 급증 → 단가 하락
k2 = korea.eval_korea(val_c, wgt_c)
check("수출단가 YoY 음수 → E1 발동", k2[0].fired)

print("="*58)
print("[D] 종합 판정")
print("="*58)
def sig(code, fired):
    from signals import Signal
    return Signal(code, code, fired, "", "", "2026-06")

st = dict(S.DEFAULT)
# 다이버전스 1개만 → 주의
v = J.judge([sig("D1",True), sig("D2",False), sig("D3",False)],
            [sig("HY",False)], [sig("E1",False)], dict(st), False)
check("다이버전스 1개 → 주의", v.level=="주의")

# 매크로 2개 → 1단계
v2 = J.judge([sig("D1",False)],
             [sig("HY",True), sig("DXY",True)], [sig("E1",False)], dict(st), False)
check("매크로 2개 → 1단계", v2.level=="1단계")

# 다이버전스 2 + 매크로 1 → 1단계
v3 = J.judge([sig("D1",True), sig("D2",True)],
             [sig("HY",True)], [sig("E1",False)], dict(st), False)
check("다이버전스2+매크로1 → 1단계", v3.level=="1단계")

# 1단계 성립 + 실물 1개 → 2단계
v4 = J.judge([sig("D1",True), sig("D2",True)],
             [sig("HY",True)], [sig("E1",True)], dict(st), True)
check("1단계+실물 → 2단계", v4.level=="2단계")

# 실물만 있고 1단계 미성립 → 실물 무시 (주의 이하)
v5 = J.judge([sig("D1",True)],
             [sig("HY",False)], [sig("E1",True)], dict(st), True)
check("1단계 미성립시 실물 단독으론 2단계 안됨", v5.level=="주의")

print("="*58)
print("[E] 해제 규칙")
print("="*58)
# 이전 2단계인데 지금 신호 다 꺼짐, 실물 미충족 1회 → 2단계 유지
st_prev2 = dict(S.DEFAULT); st_prev2["level"]="2단계"; st_prev2["kr_miss_reports"]=0
v6 = J.judge([sig("D1",False)], [sig("HY",False)], [sig("E1",False)], st_prev2, True)
check("2단계에서 실물 1회 미충족 → 2단계 유지", v6.level=="2단계")

# 실물 2회 연속 미충족 → 강등 허용
st_prev2b = dict(S.DEFAULT); st_prev2b["level"]="2단계"; st_prev2b["kr_miss_reports"]=1
v7 = J.judge([sig("D1",False)], [sig("HY",False)], [sig("E1",False)], st_prev2b, True)
check("2단계에서 실물 2회 미충족 → 강등", v7.level!="2단계")

print(f"\n🎉 전체 {PASS}개 테스트 통과")
