from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from workspace.models import RecurrenceType, Task, TaskStatus


ZONE = ZoneInfo("Asia/Tokyo")


@pytest.mark.parametrize(("kind", "expected"), [
    (RecurrenceType.DAILY, datetime(2026, 10, 3, 9, tzinfo=ZONE)),
    (RecurrenceType.WEEKLY, datetime(2026, 10, 9, 9, tzinfo=ZONE)),
    (RecurrenceType.MONTHLY, datetime(2026, 11, 2, 9, tzinfo=ZONE)),
    (RecurrenceType.INTERVAL, datetime(2026, 10, 9, 9, tzinfo=ZONE)),
])
def test_next_occurrence_types(services, user, kind, expected):
    task = Task(
        title="Recurring", created_by=user.id, recurrence_enabled=True, recurrence_type=kind,
        recurrence_interval=1, recurrence_weekdays=[4], recurrence_day_of_month=2, recurrence_time=time(9),
    )
    assert services.recurrence.next_occurrence(task, datetime(2026, 10, 2, 9, tzinfo=ZONE)) == expected


def test_month_end_clamping(services, user):
    task = Task(title="Monthly", created_by=user.id, recurrence_enabled=True,
                recurrence_type=RecurrenceType.MONTHLY, recurrence_day_of_month=31, recurrence_time=time(10))
    result = services.recurrence.next_occurrence(task, datetime(2026, 1, 31, 10, tzinfo=ZONE))
    assert result == datetime(2026, 2, 28, 10, tzinfo=ZONE)


def test_recurring_completion_advances_and_stays_active(services, user):
    task = services.tasks.save(Task(
        title="Daily", created_by=user.id, due_date=date(2026, 10, 2), due_time=time(9),
        recurrence_enabled=True, recurrence_type=RecurrenceType.DAILY, recurrence_time=time(9),
    ), user.id)
    completed = services.tasks.complete(task.id, user.id)
    assert completed.status == TaskStatus.TODO
    assert completed.due_date == date(2026, 10, 3)
    assert completed.next_occurrence_at == datetime(2026, 10, 3, 9, tzinfo=ZONE)
    assert len(services.tasks_repo.completion_history()) == 1
