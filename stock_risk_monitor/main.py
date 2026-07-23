"""
main.py
───────
진입점. 실행 순서를 제어합니다.

  python main.py --now    전체 실행 (수집 → 판정 → 발송)
  python main.py --dry    발송 없이 콘솔 출력만
  python main.py --data   수집 결과만 확인
"""

import sys
import traceback
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import sources
import divergence
import macro
import korea
import judge as judge_mod
import state as state_mod
import report


def run(dry=False):
    print("=" * 55)
    print(f"⏰ 시작 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    data = sources.collect_all()

    print("  ⚖️  판정...")
    div   = divergence.eval_divergence(data["spy"], data["rsp"], data["sox"], data["hy"])
    mac   = macro.eval_macro(data["hy"], data["dxy"], data["us10y"])
    kr    = korea.eval_korea(data["kr_value"], data["kr_weight"])

    st = state_mod.load()
    kr_month = korea.latest_report_month(data["kr_value"])
    kr_changed = bool(kr_month and kr_month != st.get("last_kr_month", ""))
    if kr_changed:
        st["last_kr_month"] = kr_month

    verdict = judge_mod.judge(div, mac, kr, st, kr_changed)
    print(f"    → 판정: {verdict.level} ({verdict.reason})")

    news = "" if dry else report.fetch_news()
    msg  = report.build_message(verdict, data, news)

    if dry:
        print("\n" + "─" * 55)
        print(msg)
        print("─" * 55)
        print("\n(--dry 모드: 발송/저장 안 함)")
        return verdict

    report.send_alert(verdict)
    report.send_telegram(msg)
    state_mod.save(st)
    print(f"🎉 완료 {datetime.now().strftime('%H:%M:%S')}")
    return verdict


def main():
    args = sys.argv[1:]
    try:
        if "--data" in args:
            d = sources.collect_all()
            for k, v in d.items():
                if hasattr(v, "__len__") and not isinstance(v, str):
                    print(f"{k}: {len(v)}건")
            return
        run(dry=("--dry" in args))
    except Exception as e:
        print(f"❌ 실행 실패: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
