"""
diagnose_customs.py
───────────────────
관세청 API 실패 원인 진단 스크립트.
로컬에서 실행:  python diagnose_customs.py

여러 조합(http/https, 인코딩/디코딩 키, 파라미터 변형)을 시도하고
실제 응답 원문을 보여줍니다.
"""

import os
import sys
from urllib.parse import unquote, quote
from datetime import datetime

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

KEY_ENV_NAMES = ["SARAMIN_KEY", "DATAGO_API_KEY", "DATA_GO_KR_KEY"]
PATH = "/1220000/nitemtrade/getNitemtradeList"


def find_key():
    for name in KEY_ENV_NAMES:
        v = os.environ.get(name, "").strip()
        if v:
            return name, v
    return None, None


def show_key_info(name, key):
    print("=" * 60)
    print("1) 인증키 형태 확인")
    print("=" * 60)
    print(f"  환경변수명 : {name}")
    print(f"  길이       : {len(key)}자")
    print(f"  앞 12자    : {key[:12]}...")
    print(f"  뒤 8자     : ...{key[-8:]}")
    has_pct = "%" in key
    has_plus = "+" in key
    has_eq  = "=" in key
    print(f"  '%' 포함   : {has_pct}   (True면 Encoding 키)")
    print(f"  '+' 포함   : {has_plus}  (True면 Decoding 키)")
    print(f"  '=' 포함   : {has_eq}")
    if has_pct:
        print("  → Encoding 키로 보입니다. requests params에 넣으면 이중 인코딩됩니다.")
    elif has_plus or has_eq:
        print("  → Decoding 키로 보입니다. requests params 사용이 맞습니다.")
    else:
        print("  → 특수문자 없음. 어느 쪽이든 무방합니다.")
    print()


def try_call(scheme, key_mode, key, cnty="US", extra=None, label=""):
    """단일 조합 시도 → (성공여부, 요약)"""
    url = f"{scheme}://apis.data.go.kr{PATH}"
    now = datetime.now()
    strt = f"{now.year}01"
    end  = now.strftime("%Y%m")

    if key_mode == "decoded":
        k = unquote(key)
    elif key_mode == "raw":
        k = key
    else:
        k = key

    params = {
        "strtYymm": strt,
        "endYymm":  end,
        "hsSgn":    "8542",
        "cntyCd":   cnty,
    }
    if extra:
        params.update(extra)

    try:
        if key_mode == "url_appended":
            # 키를 URL에 직접 붙여 requests가 재인코딩하지 않게 함
            qs = "&".join(f"{a}={b}" for a, b in params.items())
            full = f"{url}?serviceKey={key}&{qs}"
            r = requests.get(full, timeout=25)
        else:
            params["serviceKey"] = k
            r = requests.get(url, params=params, timeout=25)

        body = r.text
        item_cnt = body.count("<item>")
        # 결과 코드 추출
        code = ""
        for tag in ["resultCode", "returnReasonCode", "errMsg", "resultMsg", "returnAuthMsg"]:
            i = body.find(f"<{tag}>")
            if i != -1:
                j = body.find(f"</{tag}>", i)
                code += f"{tag}={body[i+len(tag)+2:j]}  "
        ok = item_cnt > 0
        return ok, {
            "label": label,
            "status": r.status_code,
            "items": item_cnt,
            "codes": code.strip() or "(없음)",
            "snippet": body[:300].replace("\n", " "),
        }
    except Exception as e:
        return False, {"label": label, "status": "EXC", "items": 0,
                       "codes": str(e)[:120], "snippet": ""}


def main():
    name, key = find_key()
    if not key:
        print("❌ 인증키를 찾을 수 없습니다.")
        print(f"   다음 중 하나를 환경변수 또는 .env에 설정하세요: {', '.join(KEY_ENV_NAMES)}")
        sys.exit(1)

    show_key_info(name, key)

    print("=" * 60)
    print("2) 조합별 호출 시도")
    print("=" * 60)

    combos = [
        ("https", "decoded",      "HTTPS + 디코딩키(params)"),
        ("http",  "decoded",      "HTTP  + 디코딩키(params)"),
        ("https", "raw",          "HTTPS + 원본키(params)"),
        ("http",  "raw",          "HTTP  + 원본키(params)"),
        ("https", "url_appended", "HTTPS + 키를 URL에 직접 부착"),
        ("http",  "url_appended", "HTTP  + 키를 URL에 직접 부착"),
    ]

    winners = []
    for scheme, mode, label in combos:
        ok, info = try_call(scheme, mode, key, label=label)
        mark = "✅" if ok else "❌"
        print(f"{mark} {label}")
        print(f"     HTTP {info['status']} | item {info['items']}개 | {info['codes']}")
        if not ok and info["snippet"]:
            print(f"     응답: {info['snippet'][:200]}")
        print()
        if ok:
            winners.append((scheme, mode, label))

    print("=" * 60)
    print("3) 진단 결과")
    print("=" * 60)
    if winners:
        s, m, l = winners[0]
        print(f"✅ 작동하는 조합: {l}")
        print(f"   → sources.py를 scheme={s}, key_mode={m} 으로 맞추면 됩니다.")
    else:
        print("❌ 모든 조합 실패. 아래를 순서대로 확인하세요:")
        print()
        print("   [1] 활용신청 여부 (가장 흔한 원인)")
        print("       data.go.kr 로그인 → 마이페이지 → 오픈API → 활용신청 현황")
        print("       '관세청_품목별 국가별 수출입실적(GW)'이 목록에 있고 '승인' 상태인지 확인")
        print("       없다면 아래 주소에서 활용신청 필요:")
        print("       https://www.data.go.kr/data/15100475/openapi.do")
        print()
        print("   [2] 키 반영 대기")
        print("       신규 발급 키는 반영까지 최대 1시간 소요될 수 있습니다.")
        print()
        print("   [3] 키 종류 확인")
        print("       마이페이지 상세에서 '일반 인증키(Encoding)'와 '(Decoding)' 두 가지가 있습니다.")
        print("       위 1)번 출력과 대조해보세요.")
        print()
        print("   [4] SARAMIN_KEY에 다른 서비스 키가 들어있지 않은지 확인")


if __name__ == "__main__":
    main()
