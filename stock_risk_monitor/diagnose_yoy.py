"""
diagnose_yoy.py
───────────────
관세청 월별 집계값과 YoY 계산 과정을 전부 출력해 이상 원인을 찾습니다.

사용법:
  set  SARAMIN_KEY=...        (Windows)
  export SARAMIN_KEY=...      (Mac/Linux)
  python diagnose_yoy.py

또는 .env 파일에 SARAMIN_KEY 를 넣어두면 자동으로 읽습니다.
"""

import os
import sys
import time
from urllib.parse import unquote
from datetime import datetime
import xml.etree.ElementTree as ET

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

URL = "http://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"

# 조회 대상 (필요시 수정)
HS_CODE   = os.environ.get("DIAG_HS", "854232")   # 854232=메모리, 8542=반도체전체
COUNTRIES = ["US", "TW", "CN", "HK", "JP", "SG", "MY", "VN",
             "DE", "NL", "IE", "IL", "IN", "MX"]
YEARS     = [2024, 2025, 2026]


def call(key, strt, end, cnty):
    params = {
        "serviceKey": unquote(key),
        "strtYymm":   strt,
        "endYymm":    end,
        "hsSgn":      HS_CODE,
        "cntyCd":     cnty,
    }
    r = requests.get(URL, params=params, timeout=30)
    r.raise_for_status()
    return r.content


def parse(content):
    """{'YYYY-MM': {'value':.., 'weight':..}} + 스킵된 행 수"""
    rows, skipped = {}, []
    root = ET.fromstring(content)
    for item in root.iter("item"):
        raw = (item.findtext("year") or "").strip()
        ym  = raw.replace(".", "")
        if len(ym) < 6 or not ym[:6].isdigit():
            skipped.append(raw)
            continue
        k = f"{ym[:4]}-{ym[4:6]}"
        try:
            v = float((item.findtext("expDlr") or "0").replace(",", ""))
            w = float((item.findtext("expWgt") or "0").replace(",", ""))
        except ValueError:
            continue
        if k not in rows:
            rows[k] = {"value": 0.0, "weight": 0.0, "n": 0}
        rows[k]["value"]  += v
        rows[k]["weight"] += w
        rows[k]["n"]      += 1
    return rows, skipped


def main():
    key = os.environ.get("SARAMIN_KEY", "").strip()
    if not key:
        print("❌ SARAMIN_KEY 환경변수가 없습니다.")
        sys.exit(1)

    print("=" * 72)
    print(f"조회 설정  HS={HS_CODE}  국가 {len(COUNTRIES)}개  연도 {YEARS}")
    print("=" * 72)

    merged = {}
    per_country_months = {}
    skipped_samples = set()

    for cnty in COUNTRIES:
        months_found = []
        for y in YEARS:
            strt = f"{y}01"
            end  = f"{y}12" if y != datetime.now().year else datetime.now().strftime("%Y%m")
            try:
                rows, skipped = parse(call(key, strt, end, cnty))
                skipped_samples.update(skipped)
                for k, d in rows.items():
                    if k not in merged:
                        merged[k] = {"value": 0.0, "weight": 0.0, "rows": 0}
                    merged[k]["value"]  += d["value"]
                    merged[k]["weight"] += d["weight"]
                    merged[k]["rows"]   += d["n"]
                    months_found.append(k)
            except Exception as e:
                print(f"  ✗ {cnty} {y}: {e}")
            time.sleep(0.2)
        per_country_months[cnty] = len(months_found)
        print(f"  {cnty}: {len(months_found)}개월 수집")

    print()
    print("=" * 72)
    print("스킵된 year 값 (총계 행 등)")
    print("=" * 72)
    print(" ", sorted(skipped_samples) if skipped_samples else "없음")

    print()
    print("=" * 72)
    print("월별 집계 결과")
    print("=" * 72)
    print(f"{'월':>9} {'수출액(M$)':>14} {'물량(톤)':>12} {'단가($/kg)':>12} {'행수':>5}")
    for k in sorted(merged):
        d = merged[k]
        price = d["value"] / d["weight"] if d["weight"] else 0
        print(f"{k:>9} {d['value']/1e6:>14,.1f} {d['weight']/1000:>12,.1f} "
              f"{price:>12,.1f} {d['rows']:>5}")

    print()
    print("=" * 72)
    print("YoY 계산 검증 (월 키 명시 매칭)")
    print("=" * 72)
    keys = sorted(merged)
    print(f"{'당월':>9} {'비교대상':>9} {'당월값(M$)':>13} {'전년값(M$)':>13} {'YoY':>9}")
    for k in keys:
        y, m = k.split("-")
        prev = f"{int(y)-1}-{m}"
        if prev in merged:
            cur_v, prv_v = merged[k]["value"], merged[prev]["value"]
            yoy = (cur_v - prv_v) / prv_v * 100 if prv_v else float("nan")
            flag = "  ⚠비정상" if abs(yoy) > 100 else ""
            print(f"{k:>9} {prev:>9} {cur_v/1e6:>13,.1f} {prv_v/1e6:>13,.1f} "
                  f"{yoy:>+8.1f}%{flag}")
        else:
            print(f"{k:>9} {prev:>9} {'':>13} {'전년 데이터 없음':>13}")

    print()
    print("=" * 72)
    print("결측월 점검")
    print("=" * 72)
    if keys:
        start_y, start_m = map(int, keys[0].split("-"))
        end_y,   end_m   = map(int, keys[-1].split("-"))
        expected = []
        y, m = start_y, start_m
        while (y, m) <= (end_y, end_m):
            expected.append(f"{y}-{m:02d}")
            m += 1
            if m > 12:
                m = 1; y += 1
        missing = [e for e in expected if e not in merged]
        print(f"  기대 {len(expected)}개월 / 실제 {len(keys)}개월")
        print(f"  결측: {missing if missing else '없음'}")


if __name__ == "__main__":
    main()
