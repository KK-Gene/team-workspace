from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Protocol

from workspace.clock import Clock, to_storage
from workspace.models import Task, TaskStatus, User
from workspace.repositories.notifications import NotificationOutboxRepository


LOGGER = logging.getLogger("team_workspace.notifications")


class ReminderCalculator(Protocol):
    def reminder_at(self, task: Task): ...
    def due_datetime(self, task: Task): ...


class UserLookup(Protocol):
    def find_by_id(self, user_id: int) -> User | None: ...


class PowerAutomateDeliveryError(Exception):
    pass


@dataclass(slots=True)
class PowerAutomateClient:
    webhook_url: str
    timeout_seconds: int = 10

    @property
    def configured(self) -> bool:
        return bool(self.webhook_url.strip())

    def send(self, payload: dict[str, object]) -> None:
        if not self.configured:
            raise PowerAutomateDeliveryError("Power Automate Webhookが設定されていません。")
        request = urllib.request.Request(
            self.webhook_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "TeamWorkspace/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                if not 200 <= response.status < 300:
                    raise PowerAutomateDeliveryError(f"Power Automate returned HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            raise PowerAutomateDeliveryError(f"Power Automate returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise PowerAutomateDeliveryError("Power Automateへの接続に失敗しました。") from exc


class ReminderSyncService:
    SCHEMA_VERSION = 1

    def __init__(
        self,
        outbox: NotificationOutboxRepository,
        client: PowerAutomateClient,
        reminders: ReminderCalculator,
        users: UserLookup,
        clock: Clock,
        destination_mode: str = "hybrid",
    ) -> None:
        self.outbox = outbox
        self.client = client
        self.reminders = reminders
        self.users = users
        self.clock = clock
        self.destination_mode = destination_mode if destination_mode in {"individual", "channel", "hybrid"} else "hybrid"

    @property
    def configured(self) -> bool:
        return self.client.configured

    def _notification_key(self, task: Task) -> str | None:
        if task.id is None:
            return None
        reminder_at = self.reminders.reminder_at(task)
        if reminder_at is None:
            return None
        occurrence = task.next_occurrence_at or reminder_at
        return f"task:{task.id}:{to_storage(occurrence)}:reminder"

    def _payload(self, event_id: str, key: str, action: str, task: Task) -> dict[str, object]:
        assignee = self.users.find_by_id(task.assignee_user_id) if task.assignee_user_id else None
        reminder_at = self.reminders.reminder_at(task)
        return {
            "schema_version": self.SCHEMA_VERSION,
            "event_id": event_id,
            "action": action,
            "notification_key": key,
            "source": "team-workspace",
            "occurred_at_utc": to_storage(self.clock.now()),
            "task": {
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "status": str(task.status),
                "priority": str(task.priority),
                "due_at_utc": to_storage(self.reminders.due_datetime(task)),
                "reminder_at_utc": to_storage(reminder_at),
                "occurrence_at_utc": to_storage(task.next_occurrence_at or reminder_at),
                "recurring": task.recurrence_enabled,
                "tags": task.tags,
            },
            "assignee": {
                "user_id": assignee.id if assignee else task.assignee_user_id,
                "display_name": assignee.display_name if assignee else "",
                "email": assignee.email or "" if assignee else "",
            },
            "delivery": {"mode": self.destination_mode},
        }

    def _enqueue(self, action: str, key: str, task: Task) -> int:
        event_id = str(uuid.uuid4())
        return self.outbox.enqueue(event_id, key, action, self._payload(event_id, key, action, task))

    def task_saved(self, previous: Task | None, current: Task) -> None:
        old_key = self._notification_key(previous) if previous else None
        new_key = self._notification_key(current)
        if old_key and old_key != new_key:
            self._enqueue("cancel", old_key, previous)  # type: ignore[arg-type]
        if current.status == TaskStatus.DONE or not current.reminder_enabled:
            if old_key and old_key == new_key:
                self._enqueue("cancel", old_key, current)
            return
        if new_key:
            self._enqueue("upsert", new_key, current)

    def task_deleted(self, task: Task) -> None:
        key = self._notification_key(task)
        if key:
            self._enqueue("cancel", key, task)

    def task_acknowledged(self, task: Task) -> None:
        key = self._notification_key(task)
        if key:
            self._enqueue("cancel", key, task)

    def queue_test(self, user: User) -> int:
        event_id = str(uuid.uuid4())
        key = f"test:{event_id}"
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "event_id": event_id,
            "action": "test",
            "notification_key": key,
            "source": "team-workspace",
            "occurred_at_utc": to_storage(self.clock.now()),
            "task": {
                "id": None,
                "title": "Team Workspace 接続テスト",
                "description": "Power Automateとの接続確認メッセージです。",
                "status": "Test",
                "priority": "Low",
                "due_at_utc": None,
                "reminder_at_utc": to_storage(self.clock.now()),
                "occurrence_at_utc": to_storage(self.clock.now()),
                "recurring": False,
                "tags": ["connection-test"],
            },
            "assignee": {"user_id": user.id, "display_name": user.display_name, "email": user.email or ""},
            "delivery": {"mode": "channel"},
        }
        return self.outbox.enqueue(event_id, key, "test", payload)

    def resync_tasks(self, tasks: list[Task]) -> int:
        queued = 0
        for task in tasks:
            key = self._notification_key(task)
            if key and task.reminder_enabled and task.status != TaskStatus.DONE:
                self._enqueue("upsert", key, task)
                queued += 1
        return queued

    def flush(self, limit: int = 25) -> tuple[int, int]:
        if not self.configured:
            return (0, 0)
        sent = failed = 0
        for item in self.outbox.pending(limit):
            try:
                payload = json.loads(str(item["payload_json"]))
                self.client.send(payload)
                self.outbox.mark_sent(int(item["id"]))
                sent += 1
            except Exception as exc:
                failed += 1
                attempts = int(item["attempts"]) + 1
                message = str(exc) if isinstance(exc, PowerAutomateDeliveryError) else "通知送信処理に失敗しました。"
                self.outbox.mark_failure(int(item["id"]), attempts, message)
                LOGGER.warning("Notification delivery failed for event %s: %s", item["event_id"], message)
        return sent, failed
