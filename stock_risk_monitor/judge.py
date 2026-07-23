"""
judge.py
────────
세 층의 신호를 종합해 최종 단계를 판정합니다.

  주의   = 다이버전스 ≥1  또는  매크로 ≥1
  1단계  = (다이버전스 ≥2 AND 매크로 ≥1)  또는  매크로 ≥2
  2단계  = 1단계 조건  AND  실물 확인 ≥1

해제: 각 층이 연속 미충족이면 단계를 한 칸씩 강등합니다.
"""

from dataclasses import dataclass, field
import config as C


LEVEL_ORDER = ["정상", "주의", "1단계", "2단계"]


@dataclass
class Verdict:
    level:      str = "정상"
    div_signals:   list = field(default_factory=list)
    macro_signals: list = field(default_factory=list)
    kr_signals:    list = field(default_factory=list)
    reason:     str = ""
    released:   str = ""

    def fired(self, group):
        return [s for s in group if s.fired]


def _raw_level(div, macro, kr) -> tuple:
    d = len([s for s in div   if s.fired])
    m = len([s for s in macro if s.fired])
    k = len([s for s in kr    if s.fired])

    stage1 = (d >= 2 and m >= 1) or (m >= 2)
    stage2 = stage1 and k >= 1

    if stage2:
        return "2단계", f"1단계 성립 + 실물확인 {k}개 (다이버전스 {d}, 매크로 {m})"
    if stage1:
        return "1단계", f"다이버전스 {d} · 매크로 {m} · 실물 {k}"
    if d >= 1 or m >= 1:
        return "주의", f"다이버전스 {d} · 매크로 {m}"
    return "정상", "발동 신호 없음"


def judge(div, macro, kr, state, kr_month_changed: bool) -> Verdict:
    v = Verdict(div_signals=div, macro_signals=macro, kr_signals=kr)
    raw, reason = _raw_level(div, macro, kr)

    d_fired = any(s.fired for s in div)
    m_fired = any(s.fired for s in macro)
    k_fired = any(s.fired for s in kr)

    # ── 미충족 카운터 갱신 ──
    state["div_miss_days"]   = 0 if d_fired else state.get("div_miss_days", 0) + 1
    state["macro_miss_days"] = 0 if m_fired else state.get("macro_miss_days", 0) + 1
    # 실물층은 새 발표가 나왔을 때만 카운트
    if kr_month_changed:
        state["kr_miss_reports"] = 0 if k_fired else state.get("kr_miss_reports", 0) + 1

    prev = state.get("level", "정상")

    # ── 해제 로직: 원판정이 이전보다 낮을 때, 연속 미충족이 기준 미달이면 유예 ──
    raw_idx  = LEVEL_ORDER.index(raw)
    prev_idx = LEVEL_ORDER.index(prev) if prev in LEVEL_ORDER else 0

    released_note = ""
    final = raw

    if raw_idx < prev_idx:
        # 강등하려면 연속 미충족 조건 충족 필요
        macro_ok = state["macro_miss_days"] >= C.RELEASE_DAYS
        div_ok   = state["div_miss_days"]   >= C.RELEASE_DAYS
        kr_ok    = state["kr_miss_reports"] >= C.RELEASE_KR_REPORTS

        # 이전이 2단계였다면 실물 해제가 필요, 그 외는 매크로/다이버전스 해제 기준
        if prev == "2단계" and not kr_ok:
            final = prev
            released_note = f"2단계 유지 (실물 미충족 {state['kr_miss_reports']}/{C.RELEASE_KR_REPORTS}회)"
        elif not (macro_ok or div_ok):
            # 한 칸만 강등
            final = LEVEL_ORDER[max(raw_idx, prev_idx - 1)]
            if final != raw:
                released_note = (f"{prev}→{final} 점진 강등 "
                                 f"(미충족 매크로 {state['macro_miss_days']}/{C.RELEASE_DAYS}일)")

    v.level    = final
    v.reason   = reason
    v.released = released_note
    state["level"] = final
    return v
