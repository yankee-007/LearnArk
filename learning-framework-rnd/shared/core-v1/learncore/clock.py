"""Clock with an explicit, recorded simulation mode.

Real learning needs honest timestamps. Tests need to advance time to exercise
spaced repetition. We allow the latter only through ``LEARNARK_NOW`` and every
event written while it is set is tagged ``"simulated": true`` so that simulated
scheduling evidence can never be mistaken for real elapsed learning.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

_SIM_ENV = "LEARNARK_NOW"


def _parse(value: str) -> datetime:
    value = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


def is_simulated() -> bool:
    return bool(os.environ.get(_SIM_ENV, "").strip())


def now() -> datetime:
    raw = os.environ.get(_SIM_ENV, "").strip()
    if raw:
        return _parse(raw)
    return datetime.now().astimezone()


def now_iso(timespec: str = "seconds") -> str:
    return now().isoformat(timespec=timespec)


def today() -> str:
    return now().date().isoformat()


def at_local(iso_date: str, time_of_day: str = "19:00:00") -> str:
    """Build an ISO timestamp with local offset, for simulated clocks."""
    dt = datetime.fromisoformat(f"{iso_date}T{time_of_day}")
    return dt.astimezone().isoformat(timespec="seconds")


def simulate(iso_timestamp: str | None) -> None:
    """Set or clear the simulated clock (used by tests)."""
    if iso_timestamp:
        os.environ[_SIM_ENV] = iso_timestamp
    else:
        os.environ.pop(_SIM_ENV, None)


def stamp_for_filename() -> str:
    return now().strftime("%Y%m%d-%H%M%S")


def days_between(a_iso: str, b_iso: str) -> float:
    return (_parse(b_iso) - _parse(a_iso)).total_seconds() / 86400.0


def add_days(iso: str, days: float) -> str:
    return (_parse(iso) + timedelta(days=days)).isoformat(timespec="seconds")


def human_age(iso: str | None) -> str:
    if not iso:
        return "unknown"
    try:
        delta = now() - _parse(iso)
    except ValueError:
        return "unknown"
    seconds = delta.total_seconds()
    if seconds < 90:
        return "just now"
    if seconds < 5400:
        return f"{int(seconds // 60)} min ago"
    if seconds < 172800:
        return f"{int(seconds // 3600)} h ago"
    return f"{int(seconds // 86400)} d ago"


def utc_note() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
