from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from zoneinfo import ZoneInfo


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def __init__(self, timezone_name: str = "Asia/Tokyo") -> None:
        self.zone = ZoneInfo(timezone_name)

    def now(self) -> datetime:
        return datetime.now(self.zone)


class FixedClock:
    def __init__(self, value: datetime) -> None:
        if value.tzinfo is None:
            raise ValueError("FixedClock requires a timezone-aware datetime")
        self.value = value

    def now(self) -> datetime:
        return self.value


def to_storage(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("Timezone-aware datetime required")
    return value.astimezone(timezone.utc).isoformat()


def from_storage(value: str | None, timezone_name: str = "Asia/Tokyo") -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value).astimezone(ZoneInfo(timezone_name))

