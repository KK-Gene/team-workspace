from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from workspace.models import Priority, RecurrenceType, ReminderType, Task, TaskFilters, TaskStatus


def test_create_title_only(services, user):
    task = services.tasks.save(Task(title="Investigate result", created_by=user.id, assignee_user_id=user.id), user.id)
    assert task.id
    assert task.title == "Investigate result"
    assert task.due_date is None


def test_due_date_and_time_assignment_priority_status(services, user):
    task = services.tasks.save(Task(
        title="Review", created_by=user.id, assignee_user_id=user.id,
        due_date=date(2026, 10, 3), due_time=time(17), priority=Priority.HIGH,
        status=TaskStatus.IN_PROGRESS, tags=["review", "spec"],
    ), user.id)
    loaded = services.tasks.get(task.id)
    assert loaded.due_date == date(2026, 10, 3)
    assert loaded.due_time == time(17)
    assert loaded.assignee_user_id == user.id
    assert loaded.priority == Priority.HIGH
    assert loaded.status == TaskStatus.IN_PROGRESS
    assert loaded.tags == ["review", "spec"]


def test_my_day_overdue_and_today(services, user):
    services.tasks.save(Task(title="Late", created_by=user.id, assignee_user_id=user.id, due_date=date(2026, 10, 1)), user.id)
    services.tasks.save(Task(title="Today", created_by=user.id, assignee_user_id=user.id, due_date=date(2026, 10, 2)), user.id)
    day = services.tasks.my_day(user.id)
    assert [item.title for item in day["overdue"]] == ["Late"]
    assert [item.title for item in day["today"]] == ["Today"]


def test_one_time_completion(services, user):
    task = services.tasks.save(Task(title="Once", created_by=user.id), user.id)
    completed = services.tasks.complete(task.id, user.id)
    assert completed.status == TaskStatus.DONE
    assert completed.last_completed_at is not None
    assert services.tasks_repo.completion_history()[0]["title"] == "Once"


def test_task_filtering(services, user):
    services.tasks.save(Task(title="Alpha", created_by=user.id, priority=Priority.CRITICAL), user.id)
    services.tasks.save(Task(title="Beta", created_by=user.id, priority=Priority.LOW), user.id)
    found = services.tasks.list(TaskFilters(priorities=[Priority.CRITICAL], text="Alp"))
    assert [item.title for item in found] == ["Alpha"]

