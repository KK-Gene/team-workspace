from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import StrEnum


class TaskStatus(StrEnum):
    BACKLOG = "Backlog"
    TODO = "Todo"
    IN_PROGRESS = "In Progress"
    BLOCKED = "Blocked"
    DONE = "Done"


class Priority(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class ReminderType(StrEnum):
    ABSOLUTE = "Absolute"
    RELATIVE = "Relative"


class RecurrenceType(StrEnum):
    DAILY = "Daily"
    WEEKLY = "Weekly"
    MONTHLY = "Monthly"
    INTERVAL = "Interval"


@dataclass(slots=True)
class User:
    username: str
    display_name: str
    id: int | None = None
    email: str | None = None
    role: str = "Member"
    active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class Task:
    title: str
    created_by: int
    id: int | None = None
    description: str = ""
    status: str = TaskStatus.TODO
    priority: str = Priority.MEDIUM
    assignee_user_id: int | None = None
    start_date: date | None = None
    due_date: date | None = None
    due_time: time | None = None
    reminder_enabled: bool = False
    reminder_type: str | None = None
    reminder_datetime: datetime | None = None
    reminder_offset_minutes: int | None = None
    reminder_acknowledged_at: datetime | None = None
    recurrence_enabled: bool = False
    recurrence_type: str | None = None
    recurrence_interval: int = 1
    recurrence_weekdays: list[int] = field(default_factory=list)
    recurrence_day_of_month: int | None = None
    recurrence_time: time | None = None
    last_completed_at: datetime | None = None
    next_occurrence_at: datetime | None = None
    tags: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class TaskFilters:
    assignee_user_id: int | None = None
    statuses: list[str] = field(default_factory=list)
    priorities: list[str] = field(default_factory=list)
    due_from: date | None = None
    due_to: date | None = None
    recurring_only: bool = False
    reminder_only: bool = False
    tag: str | None = None
    text: str | None = None

