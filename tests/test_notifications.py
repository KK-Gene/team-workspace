from __future__ import annotations

from datetime import date, timedelta

from workspace.models import ReminderType, Task


class FakePowerAutomateClient:
    def __init__(self, fail: bool = False) -> None:
        self.configured = True
        self.fail = fail
        self.payloads: list[dict[str, object]] = []

    def send(self, payload: dict[str, object]) -> None:
        if self.fail:
            raise RuntimeError("delivery failed")
        self.payloads.append(payload)


def reminder_task(user, now, title: str = "Reminder") -> Task:
    return Task(
        title=title,
        created_by=user.id,
        assignee_user_id=user.id,
        due_date=now.date() + timedelta(days=1),
        reminder_enabled=True,
        reminder_type=ReminderType.RELATIVE,
        reminder_offset_minutes=60,
    )


def test_task_save_queues_power_automate_upsert(services, user, now):
    task = services.tasks.save(reminder_task(user, now), user.id)
    rows = services.notification_outbox.recent()
    assert len(rows) == 1
    assert rows[0]["action"] == "upsert"
    assert rows[0]["status"] == "Pending"
    assert f"task:{task.id}:" in rows[0]["notification_key"]


def test_flush_sends_payload_and_marks_sent(services, user, now):
    services.tasks.save(reminder_task(user, now), user.id)
    fake = FakePowerAutomateClient()
    services.reminder_sync.client = fake
    sent, failed = services.reminder_sync.flush()
    assert (sent, failed) == (1, 0)
    assert fake.payloads[0]["schema_version"] == 1
    assert fake.payloads[0]["action"] == "upsert"
    assert services.notification_outbox.summary()["Sent"] == 1


def test_task_update_supersedes_old_pending_event(services, user, now):
    task = services.tasks.save(reminder_task(user, now), user.id)
    task.title = "Updated reminder"
    services.tasks.save(task, user.id)
    summary = services.notification_outbox.summary()
    assert summary["Pending"] == 1
    assert summary["Superseded"] == 1


def test_task_delete_queues_cancel(services, user, now):
    task = services.tasks.save(reminder_task(user, now), user.id)
    services.tasks.delete(task.id, user.id)
    rows = services.notification_outbox.recent()
    assert rows[0]["action"] == "cancel"
    assert rows[0]["status"] == "Pending"


def test_failed_delivery_is_retained_for_retry(services, user, now):
    services.tasks.save(reminder_task(user, now), user.id)
    services.reminder_sync.client = FakePowerAutomateClient(fail=True)
    sent, failed = services.reminder_sync.flush()
    assert (sent, failed) == (0, 1)
    row = services.notification_outbox.recent()[0]
    assert row["status"] == "Pending"
    assert row["attempts"] == 1
    assert row["last_error"]


def test_connection_test_payload(services, user):
    fake = FakePowerAutomateClient()
    services.reminder_sync.client = fake
    services.reminder_sync.queue_test(user)
    assert services.reminder_sync.flush() == (1, 0)
    assert fake.payloads[0]["action"] == "test"
    assert fake.payloads[0]["delivery"] == {"mode": "channel"}


def test_resync_existing_reminders(services, user, now):
    task = services.tasks.save(reminder_task(user, now), user.id)
    fake = FakePowerAutomateClient()
    services.reminder_sync.client = fake
    assert services.reminder_sync.resync_tasks([task]) == 1
    assert services.reminder_sync.flush() == (1, 0)
    assert len(fake.payloads) == 1


def test_assignee_email_is_in_payload(services, user, now):
    services.user_service.update_user(user.id, user.display_name, "tester@example.com", "Admin", True)
    services.tasks.save(reminder_task(user, now), user.id)
    fake = FakePowerAutomateClient()
    services.reminder_sync.client = fake
    services.reminder_sync.flush()
    assert fake.payloads[0]["assignee"]["email"] == "tester@example.com"
