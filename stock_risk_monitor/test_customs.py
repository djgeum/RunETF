"""관세청 국가별 합산 검증 (네트워크 없이 모의 응답 사용)"""
import os, sys
import pandas as pd
os.environ["SARAMIN_KEY"] = "DUMMY"
import sources, config as C

def mk_xml(rows):
    """rows = [(year, expDlr, expWgt)]"""
    items = "".join(
        f"<item><year>{y}</year><expDlr>{d}</expDlr><expWgt>{w}</expWgt>"
        f"<hsCd>8542</hsCd></item>" for y, d, w in rows)
    return f"<response><header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header><body><items>{items}</items></body></response>".encode()

PASS = 0
def check(name, cond):
    global PASS
    assert cond, f"❌ {name}"
    PASS += 1
    print(f"✅ {name}")

print("="*58)
print("[1] XML 파싱")
print("="*58)
xml = mk_xml([("2026.05", "1000", "10"), ("2026.06", "2000", "20")])
p = sources._parse_customs_xml(xml)
check("YYYY.MM → YYYY-MM 변환", "2026-05" in p and "2026-06" in p)
check("금액 파싱", p["2026-05"]["value"] == 1000.0)
check("중량 파싱", p["2026-05"]["weight"] == 10.0)

# 같은 월 여러 행(10단위 세번) 합산
xml2 = mk_xml([("2026.06", "1000", "10"), ("2026.06", "500", "5")])
p2 = sources._parse_customs_xml(xml2)
check("동일월 복수행 합산", p2["2026-06"]["value"] == 1500.0 and p2["2026-06"]["weight"] == 15.0)

# 콤마 포함 숫자
xml3 = mk_xml([("2026.06", "1,234,567", "12,345")])
p3 = sources._parse_customs_xml(xml3)
check("콤마 포함 숫자 파싱", p3["2026-06"]["value"] == 1234567.0)

print("="*58)
print("[2] 국가별 합산")
print("="*58)
# 국가마다 다른 값 반환하도록 모킹
CALLS = []
def fake_call(key, strt, end, cnty):
    CALLS.append((cnty, strt, end))
    # 각 국가가 2026-06에 금액 100, 중량 1 씩 기여
    if strt.startswith("2026"):
        return mk_xml([("2026.06", "100", "1")])
    return mk_xml([])   # 과거 연도는 빈 응답

sources._customs_call = fake_call
# 테스트용으로 국가 3개만
orig = C.KOREA_COUNTRIES
C.KOREA_COUNTRIES = ["US", "TW", "CN"]

res = sources.fetch_korea_export()
v = res["value"]
check("3개국 × 100 = 300 합산", float(v.loc["2026-06"]) == 300.0)
check("중량 3개국 합산", float(res["weight"].loc["2026-06"]) == 3.0)
check("coverage 3개국 기록", set(res["coverage"]) == {"US","TW","CN"})
check("국가당 3개 기간 호출", len([c for c in CALLS if c[0]=="US"]) == 3)

print("="*58)
print("[3] 실패 국가 허용")
print("="*58)
def flaky_call(key, strt, end, cnty):
    if cnty == "CN":
        raise RuntimeError("타임아웃 모의")
    if strt.startswith("2026"):
        return mk_xml([("2026.06", "100", "1")])
    return mk_xml([])

sources._customs_call = flaky_call
res2 = sources.fetch_korea_export()
check("1개국 실패해도 나머지로 진행", float(res2["value"].loc["2026-06"]) == 200.0)
check("실패 국가는 coverage 제외", "CN" not in res2["coverage"])

print("="*58)
print("[4] 대량 실패 시 안전 차단")
print("="*58)
def dead_call(key, strt, end, cnty):
    raise RuntimeError("전체 장애 모의")
sources._customs_call = dead_call
C.KOREA_COUNTRIES = orig          # 14개국 복원
res3 = sources.fetch_korea_export()
check("전부 실패 시 빈 Series 반환", len(res3["value"]) == 0)

print("="*58)
print("[5] 최신월 미완료 제외")
print("="*58)
def partial_call(key, strt, end, cnty):
    if cnty != "US":
        return mk_xml([])
    # 2026-05는 정상 1000, 2026-06은 집계중이라 100만
    if strt.startswith("2026"):
        return mk_xml([("2026.04","1000","10"), ("2026.05","1000","10"), ("2026.06","100","1")])
    return mk_xml([])
sources._customs_call = partial_call
C.KOREA_COUNTRIES = ["US"]
res4 = sources.fetch_korea_export()
check("집계 미완료 최신월 자동 제외", "2026-06" not in res4["value"].index)
check("정상월은 유지", "2026-05" in res4["value"].index)

C.KOREA_COUNTRIES = orig
print(f"\n🎉 전체 {PASS}개 통과")
