"""Parse explicit learner time statements (minutes are the storage unit)."""

from __future__ import annotations

import re

_CN = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _number(raw: str) -> float | None:
    raw = (raw or "").strip()
    try:
        return float(raw)
    except ValueError:
        pass
    if raw == "半":
        return 0.5
    if raw in _CN:
        return float(_CN[raw])
    if "十" in raw:
        left, _, right = raw.partition("十")
        tens = _CN.get(left, 1) if left else 1
        ones = _CN.get(right, 0) if right else 0
        return float(tens * 10 + ones)
    return None


_NUM = r"(?:\d+(?:\.\d+)?|[零一二两三四五六七八九十半]+)"
_WEEK = r"(?:每周|一周|这周|每个星期|每星期)"
_HOUR = r"(?:个)?(?:小时|钟头)"


def parse_learner_time(text: str) -> dict:
    raw = (text or "").strip()
    result: dict = {}
    if not raw:
        return result
    # weekly range: 每周 1–2 小时
    match = re.search(_WEEK + r"[^。；，,]{0,8}?(" + _NUM + r")\s*[-–~至到]\s*(" + _NUM + r")\s*" + _HOUR, raw)
    if match:
        low, high = _number(match.group(1)), _number(match.group(2))
        if low is not None and high is not None:
            low, high = sorted((low, high))
            result["weekly_range_minutes"] = [int(low * 60), int(high * 60)]
            result["weekly_minutes"] = int(high * 60)
    if "weekly_minutes" not in result:
        match = re.search(_WEEK + r"[^。；，,]{0,8}?(" + _NUM + r")\s*" + _HOUR, raw)
        if match:
            value = _number(match.group(1))
            if value is not None:
                result["weekly_minutes"] = int(value * 60)
        else:
            match = re.search(_WEEK + r"[^。；，,]{0,8}?(\d+)\s*分钟", raw)
            if match:
                result["weekly_minutes"] = int(match.group(1))
    # today's budget: 今天只有 20 分钟 / 今天二十分钟
    match = re.search(r"今天[^。；，,]{0,10}?(" + _NUM + r")\s*分钟", raw)
    if not match:
        match = re.search(r"今天[^。；，,]{0,6}?只有\s*(" + _NUM + r")", raw)
    if match:
        value = _number(match.group(1))
        if value is not None and value > 0:
            result["today_minutes"] = int(value)
    # 还有 10 分钟 / 只剩 15 分钟
    match = re.search(r"(?:还有|只剩|剩下)\s*(" + _NUM + r")\s*分钟", raw)
    if match and "today_minutes" not in result:
        value = _number(match.group(1))
        if value is not None and value > 0:
            result["today_minutes"] = int(value)
    return result


def estimate_minutes(text: str, default: int = 20) -> int:
    raw = text or ""
    match = re.search(r"(\d+)\s*分钟", raw)
    if match:
        return max(1, min(120, int(match.group(1))))
    match = re.search(r"(" + _NUM + r")\s*分钟", raw)
    if match:
        value = _number(match.group(1))
        if value:
            return max(1, min(120, int(value)))
    if "半小时" in raw:
        return 30
    if "十分钟" in raw or "10 分钟" in raw:
        return 10
    return default
