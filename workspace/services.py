from __future__ import annotations

import calendar
import csv
import getpass
import io
import logging
import sqlite3
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from pathlib import Path
from contextlib import closing
from typing import Any
from zoneinfo import ZoneInfo

from workspace.clock import Clock, to_storage
from workspace.database import Database
from workspace.errors import ValidationError
from workspace.models import Priority, RecurrenceType, ReminderType, Task, TaskFilters, TaskStatus, User
from workspace.repositories.content import ActivityRepository, ContentRepository, FavoriteRepository
from workspace.repositories.interfaces import (
    ActivityRepositoryProtocol,
    ContentRepositoryProtocol,
    TaskRepositoryProtocol,
    UserRepositoryProtocol,
)
from workspace.repositories.search import SearchRepository
from workspace.repositories.tasks import TaskRepository
from workspace.repositories.users import UserRepository


LOGGER = logging.getLogger("team_workspace.services")


def parse_tags(value: str | list[str]) -> list[str]:
    source = value if isinstance(value, list) else value.replace("、", ",").split(",")
    return sorted({str(item).strip() for item in source if str(item).strip()}, key=str.casefold)


class UserService:
    def __init__(self, repository: UserRepositoryProtocol) -> None:
        self.repository = repository

    def current_user(self) -> User:
        username = getpass.getuser().strip() or "local-user"
        existing = self.repository.find_by_username(username)
        if existing:
            if not existing.active:
                raise ValidationError("現在のユーザーは無効化されています。管理者に連絡してください。")
            return existing
        role = "Admin" if not self.repository.list_all() else "Member"
        return self.repository.save(User(username=username, display_name=username, role=role))

    def add_user(self, username: str, display_name: str, email: str = "", role: str = "Member") -> User:
        if not username.strip() or not display_name.strip():
            raise ValidationError("ユーザー名と表示名は必須です。")
        return self.repository.save(User(username=username, display_name=display_name, email=email or None, role=role))


class RecurrenceService:
    def __init__(self, timezone_name: str = "Asia/Tokyo") -> None:
        self.zone = ZoneInfo(timezone_name)

    @staticmethod
    def _add_months(value: datetime, months: int, day: int) -> datetime:
        absolute_month = value.year * 12 + value.month - 1 + months
        year, month_index = divmod(absolute_month, 12)
        month = month_index + 1
        valid_day = min(day, calendar.monthrange(year, month)[1])
        return value.replace(year=year, month=month, day=valid_day)

    def next_occurrence(self, task: Task, after: datetime) -> datetime:
        if not task.recurrence_enabled or not task.recurrence_type:
            raise ValidationError("繰り返し設定がありません。")
        if after.tzinfo is None:
            after = after.replace(tzinfo=self.zone)
        interval = max(1, task.recurrence_interval)
        occurrence_time = task.recurrence_time or task.due_time or time(9, 0)
        current = after.astimezone(self.zone)
        kind = str(task.recurrence_type)
        if kind == RecurrenceType.DAILY:
            candidate = current + timedelta(days=interval)
            return candidate.replace(hour=occurrence_time.hour, minute=occurrence_time.minute, second=0, microsecond=0)
        if kind == RecurrenceType.INTERVAL:
            candidate = current + timedelta(weeks=interval)
            return candidate.replace(hour=occurrence_time.hour, minute=occurrence_time.minute, second=0, microsecond=0)
        if kind == RecurrenceType.MONTHLY:
            day = task.recurrence_day_of_month or current.day
            candidate = self._add_months(current, interval, day)
            return candidate.replace(hour=occurrence_time.hour, minute=occurrence_time.minute, second=0, microsecond=0)
        if kind == RecurrenceType.WEEKLY:
            weekdays = sorted(set(task.recurrence_weekdays or [current.weekday()]))
            start = current.date()
            if interval == 1:
                for offset in range(1, 8):
                    candidate_date = start + timedelta(days=offset)
                    if candidate_date.weekday() in weekdays:
                        return datetime.combine(candidate_date, occurrence_time, self.zone)
            current_week_start = start - timedelta(days=start.weekday())
            target_week_start = current_week_start + timedelta(weeks=interval)
            target = target_week_start + timedelta(days=weekdays[0])
            return datetime.combine(target, occurrence_time, self.zone)
        raise ValidationError(f"未対応の繰り返し種別です: {kind}")


class ReminderService:
    def __init__(self, clock: Clock, timezone_name: str = "Asia/Tokyo") -> None:
        self.clock = clock
        self.zone = ZoneInfo(timezone_name)

    def due_datetime(self, task: Task) -> datetime | None:
        if not task.due_date:
            return None
        due_time = task.due_time or time(23, 59, 59)
        return datetime.combine(task.due_date, due_time, self.zone)

    def reminder_at(self, task: Task) -> datetime | None:
        if not task.reminder_enabled:
            return None
        if task.reminder_type == ReminderType.ABSOLUTE:
            return task.reminder_datetime
        if task.reminder_type == ReminderType.RELATIVE:
            due = self.due_datetime(task)
            if due is None or task.reminder_offset_minutes is None:
                return None
            return due - timedelta(minutes=task.reminder_offset_minutes)
        return None

    def is_due(self, task: Task) -> bool:
        reminder = self.reminder_at(task)
        return bool(
            reminder and reminder <= self.clock.now() and task.status != TaskStatus.DONE
            and task.reminder_acknowledged_at is None
        )

    def due_reminders(self, tasks: list[Task]) -> list[Task]:
        return sorted((task for task in tasks if self.is_due(task)), key=lambda item: self.reminder_at(item) or self.clock.now())


class TaskService:
    def __init__(self, repository: TaskRepositoryProtocol, activity: ActivityRepositoryProtocol, recurrence: RecurrenceService,
                 reminders: ReminderService, clock: Clock, timezone_name: str = "Asia/Tokyo") -> None:
        self.repository = repository
        self.activity = activity
        self.recurrence = recurrence
        self.reminders = reminders
        self.clock = clock
        self.zone = ZoneInfo(timezone_name)

    def save(self, task: Task, actor_id: int) -> Task:
        if not task.title.strip():
            raise ValidationError("タイトルは必須です。")
        if task.recurrence_enabled and not task.recurrence_type:
            raise ValidationError("繰り返し種別を選択してください。")
        if task.reminder_enabled and task.reminder_type == ReminderType.RELATIVE and not task.due_date:
            raise ValidationError("相対リマインダーには期限日が必要です。")
        if task.reminder_enabled and task.reminder_type == ReminderType.ABSOLUTE and not task.reminder_datetime:
            raise ValidationError("絶対リマインダーの日時を指定してください。")
        action = "created" if task.id is None else "updated"
        if task.recurrence_enabled and task.due_date and task.next_occurrence_at is None:
            task.next_occurrence_at = datetime.combine(
                task.due_date, task.recurrence_time or task.due_time or time(9), self.zone
            )
        saved = self.repository.save(task)
        self.activity.add(actor_id, action, "task", saved.id, saved.title)
        return saved

    def delete(self, task_id: int, actor_id: int) -> None:
        task = self.get(task_id)
        self.repository.delete(task_id)
        self.activity.add(actor_id, "deleted", "task", task_id, task.title)

    def get(self, task_id: int) -> Task:
        task = self.repository.find_by_id(task_id)
        if not task:
            raise ValidationError("タスクが見つかりません。")
        return task

    def list(self, filters: TaskFilters | None = None) -> list[Task]:
        return self.repository.find_all(filters)

    def complete(self, task_id: int, actor_id: int) -> Task:
        task = self.get(task_id)
        now = self.clock.now()
        scheduled = task.next_occurrence_at or self.reminders.due_datetime(task)
        task.last_completed_at = now
        if task.recurrence_enabled:
            anchor = scheduled or now
            next_at = self.recurrence.next_occurrence(task, anchor)
            task.next_occurrence_at = next_at
            local = next_at.astimezone(self.zone)
            task.due_date = local.date()
            task.due_time = local.time().replace(second=0, microsecond=0)
            task.status = TaskStatus.TODO
            task.reminder_acknowledged_at = None
        else:
            task.status = TaskStatus.DONE
        saved = self.repository.record_completion(task, actor_id, to_storage(scheduled))
        self.activity.add(actor_id, "completed", "task", saved.id, saved.title)
        return saved

    def acknowledge_reminder(self, task_id: int, actor_id: int) -> Task:
        task = self.get(task_id)
        task.reminder_acknowledged_at = self.clock.now()
        saved = self.repository.save(task)
        self.activity.add(actor_id, "acknowledged reminder", "task", saved.id, saved.title)
        return saved

    def my_day(self, user_id: int) -> dict[str, list[Task]]:
        today = self.clock.now().astimezone(self.zone).date()
        tasks = self.list(TaskFilters(assignee_user_id=user_id))
        active = [task for task in tasks if task.status != TaskStatus.DONE]
        return {
            "overdue": [task for task in active if task.due_date and task.due_date < today],
            "critical": [task for task in active if task.priority == Priority.CRITICAL],
            "reminders": self.reminders.due_reminders(active),
            "today": [task for task in active if task.due_date == today],
            "recurring": [task for task in active if task.recurrence_enabled],
        }


class ContentService:
    def __init__(self, repository: ContentRepositoryProtocol, activity: ActivityRepositoryProtocol) -> None:
        self.repository = repository
        self.activity = activity

    def save(self, values: dict[str, Any], actor_id: int, entity_id: int | None = None) -> dict[str, Any]:
        title_field = "term" if self.repository.entity_type == "glossary" else "title"
        if not str(values.get(title_field, "")).strip():
            raise ValidationError("タイトルまたは用語は必須です。")
        if self.repository.entity_type in ("snippet", "note", "glossary"):
            body = {"snippet": "content", "note": "content", "glossary": "definition"}[self.repository.entity_type]
            if not str(values.get(body, "")).strip():
                raise ValidationError("本文または定義は必須です。")
        values["created_by"] = actor_id
        values["tags"] = parse_tags(values.get("tags", []))
        action = "created" if entity_id is None else "updated"
        saved = self.repository.save(values, entity_id)
        self.activity.add(actor_id, action, self.repository.entity_type, saved["id"], str(saved[title_field]))
        return saved

    def delete(self, entity_id: int, actor_id: int) -> None:
        item = self.repository.find_by_id(entity_id)
        if not item:
            raise ValidationError("対象データが見つかりません。")
        title_field = "term" if self.repository.entity_type == "glossary" else "title"
        self.repository.delete(entity_id)
        self.activity.add(actor_id, "deleted", self.repository.entity_type, entity_id, str(item[title_field]))


class BackupService:
    def __init__(self, database: Database, backup_dir: Path, clock: Clock, retention: int = 15) -> None:
        self.database = database
        self.backup_dir = backup_dir
        self.clock = clock
        self.retention = retention

    def latest(self) -> Path | None:
        backups = sorted(self.backup_dir.glob("workspace_*.db"), key=lambda path: path.stat().st_mtime, reverse=True)
        return backups[0] if backups else None

    def create(self) -> Path:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        filename = self.clock.now().strftime("workspace_%Y%m%d_%H%M%S.db")
        destination = self.backup_dir / filename
        temporary = destination.with_suffix(".tmp")
        try:
            with self.database.connection() as source:
                with closing(sqlite3.connect(temporary)) as target:
                    source.backup(target)
            with closing(sqlite3.connect(temporary)) as check:
                if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Backup integrity check failed")
            temporary.replace(destination)
            backups = sorted(self.backup_dir.glob("workspace_*.db"), key=lambda path: path.stat().st_mtime, reverse=True)
            for old in backups[self.retention:]:
                old.unlink()
            LOGGER.info("Created database backup %s", destination)
            return destination
        except Exception:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                LOGGER.warning("Could not remove failed temporary backup %s", temporary)
            LOGGER.exception("Backup failed")
            raise

    def create_if_due(self, interval_hours: int) -> Path | None:
        latest = self.latest()
        if latest:
            age = self.clock.now().timestamp() - latest.stat().st_mtime
            if age < interval_hours * 3600:
                return None
        return self.create()


class ExportService:
    TABLES = {
        "tasks": "tasks", "snippets": "snippets", "links": "links",
        "glossary": "glossary_entries", "notes": "notes",
    }

    def __init__(self, database: Database) -> None:
        self.database = database

    def csv_bytes(self, name: str) -> bytes:
        if name not in self.TABLES:
            raise ValidationError("未対応のエクスポートです。")
        rows = self.database.read(lambda connection: connection.execute(
            f"SELECT * FROM {self.TABLES[name]} ORDER BY id"
        ).fetchall())
        output = io.StringIO(newline="")
        if rows:
            writer = csv.DictWriter(output, fieldnames=rows[0].keys())
            writer.writeheader(); writer.writerows(dict(row) for row in rows)
        return output.getvalue().encode("utf-8-sig")


class AppServices:
    def __init__(self, database: Database, clock: Clock, backup_dir: Path, timezone_name: str,
                 backup_retention: int = 15) -> None:
        self.database = database
        self.clock = clock
        self.activity = ActivityRepository(database, clock)
        self.users = UserRepository(database, clock)
        self.user_service = UserService(self.users)
        self.tasks_repo = TaskRepository(database, clock)
        self.reminders = ReminderService(clock, timezone_name)
        self.recurrence = RecurrenceService(timezone_name)
        self.tasks = TaskService(self.tasks_repo, self.activity, self.recurrence, self.reminders, clock, timezone_name)
        self.content_repositories = {
            kind: ContentRepository(database, clock, kind) for kind in ("snippet", "link", "glossary", "note")
        }
        self.content = {kind: ContentService(repo, self.activity) for kind, repo in self.content_repositories.items()}
        self.favorites = FavoriteRepository(database, clock)
        self.search = SearchRepository(database)
        self.backups = BackupService(database, backup_dir, clock, backup_retention)
        self.exports = ExportService(database)
