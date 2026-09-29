from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from workspace.models import ReminderType, Task


ZONE = ZoneInfo("Asia/Tokyo")


def test_absolute_reminder_due(services, user, now):
    task = Task(title="Call", created_by=user.id, reminder_enabled=True,
                reminder_type=ReminderType.ABSOLUTE, reminder_datetime=now - timedelta(minutes=1))
    assert services.reminders.is_due(task)


def test_relative_reminder_offset(services, user):
    task = Task(title="Review", created_by=user.id, due_date=date(2026, 10, 2), due_time=time(13),
                reminder_enabled=True, reminder_type=ReminderType.RELATIVE, reminder_offset_minutes=60)
    assert services.reminders.reminder_at(task) == datetime(2026, 10, 2, 12, tzinfo=ZONE)
    assert services.reminders.is_due(task)


def test_date_only_uses_end_of_day(services, user):
    task = Task(title="Date only", created_by=user.id, due_date=date(2026, 10, 2),
                reminder_enabled=True, reminder_type=ReminderType.RELATIVE, reminder_offset_minutes=60)
    assert services.reminders.reminder_at(task) == datetime(2026, 10, 2, 22, 59, 59, tzinfo=ZONE)


def test_acknowledged_reminder_is_hidden(services, user, now):
    task = services.tasks.save(Task(title="Call", created_by=user.id, reminder_enabled=True,
        reminder_type=ReminderType.ABSOLUTE, reminder_datetime=now - timedelta(minutes=1)), user.id)
    acknowledged = services.tasks.acknowledge_reminder(task.id, user.id)
    assert not services.reminders.is_due(acknowledged)

