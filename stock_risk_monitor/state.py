"""
state.py
────────
이전 판정을 기억합니다. 해제 규칙(연속 미충족 시 강등)에 사용됩니다.
data/risk_state.json 에 저장됩니다.
"""

import os
import json
from datetime import datetime

import config as C

DEFAULT = {
    "level": "정상",
    "div_miss_days":   0,   # 다이버전스 미충족 연속 실행 횟수
    "macro_miss_days": 0,   # 매크로 미충족 연속 실행 횟수
    "kr_miss_reports": 0,   # 실물 미충족 연속 발표 횟수
    "last_kr_month":   "",  # 마지막으로 처리한 관세청 발표월
    "updated_at":      "",
}


def load(path: str = None) -> dict:
    path = path or C.STATE_PATH
    if not os.path.exists(path):
        return dict(DEFAULT)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULT)
        merged.update(data)
        return merged
    except Exception as e:
        print(f"    [state] 읽기 실패, 기본값 사용: {e}")
        return dict(DEFAULT)


def save(state: dict, path: str = None) -> None:
    path = path or C.STATE_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print(f"    [state] 저장 완료 → {path}")
