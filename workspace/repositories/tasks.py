from __future__ import annotations

import sqlite3
from datetime import date, time

from workspace.clock import Clock, from_storage, to_storage
from workspace.database import Database
from workspace.models import Task, TaskFilters


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _time(value: str | None) -> time | None:
    return time.fromisoformat(value) if value else None


class TaskRepository:
    def __init__(self, database: Database, clock: Clock) -> None:
        self.database = database
        self.clock = clock

    def _map(self, connection: sqlite3.Connection, row: sqlite3.Row | None) -> Task | None:
        if row is None:
            return None
        tags = [tag[0] for tag in connection.execute(
            "SELECT t.name FROM tags t JOIN entity_tags et ON et.tag_id=t.id "
            "WHERE et.entity_type='task' AND et.entity_id=? ORDER BY t.name", (row["id"],)
        ).fetchall()]
        weekdays = [int(item) for item in (row["recurrence_weekdays"] or "").split(",") if item != ""]
        return Task(
            id=row["id"], title=row["title"], description=row["description"], status=row["status"],
            priority=row["priority"], assignee_user_id=row["assignee_user_id"], created_by=row["created_by"],
            start_date=_date(row["start_date"]), due_date=_date(row["due_date"]), due_time=_time(row["due_time"]),
            reminder_enabled=bool(row["reminder_enabled"]), reminder_type=row["reminder_type"],
            reminder_datetime=from_storage(row["reminder_datetime"]),
            reminder_offset_minutes=row["reminder_offset_minutes"],
            reminder_acknowledged_at=from_storage(row["reminder_acknowledged_at"]),
            recurrence_enabled=bool(row["recurrence_enabled"]), recurrence_type=row["recurrence_type"],
            recurrence_interval=row["recurrence_interval"], recurrence_weekdays=weekdays,
            recurrence_day_of_month=row["recurrence_day_of_month"], recurrence_time=_time(row["recurrence_time"]),
            last_completed_at=from_storage(row["last_completed_at"]), next_occurrence_at=from_storage(row["next_occurrence_at"]),
            tags=tags, created_at=from_storage(row["created_at"]), updated_at=from_storage(row["updated_at"]),
        )

    def find_by_id(self, task_id: int) -> Task | None:
        def select(connection: sqlite3.Connection) -> Task | None:
            return self._map(connection, connection.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())
        return self.database.read(select)

    def find_all(self, filters: TaskFilters | None = None) -> list[Task]:
        filters = filters or TaskFilters()
        clauses: list[str] = []
        parameters: list[object] = []
        if filters.assignee_user_id is not None:
            clauses.append("t.assignee_user_id=?"); parameters.append(filters.assignee_user_id)
        if filters.statuses:
            clauses.append(f"t.status IN ({','.join('?' for _ in filters.statuses)})"); parameters.extend(filters.statuses)
        if filters.priorities:
            clauses.append(f"t.priority IN ({','.join('?' for _ in filters.priorities)})"); parameters.extend(filters.priorities)
        if filters.due_from:
            clauses.append("t.due_date>=?"); parameters.append(filters.due_from.isoformat())
        if filters.due_to:
            clauses.append("t.due_date<=?"); parameters.append(filters.due_to.isoformat())
        if filters.recurring_only:
            clauses.append("t.recurrence_enabled=1")
        if filters.reminder_only:
            clauses.append("t.reminder_enabled=1")
        if filters.text:
            clauses.append("(t.title LIKE ? OR t.description LIKE ?)")
            pattern = f"%{filters.text}%"; parameters.extend((pattern, pattern))
        if filters.tag:
            clauses.append("EXISTS(SELECT 1 FROM entity_tags et JOIN tags tg ON tg.id=et.tag_id "
                           "WHERE et.entity_type='task' AND et.entity_id=t.id AND tg.name=? COLLATE NOCASE)")
            parameters.append(filters.tag)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = "SELECT t.* FROM tasks t" + where + " ORDER BY t.due_date IS NULL, t.due_date, t.due_time, t.id DESC"

        def select(connection: sqlite3.Connection) -> list[Task]:
            return [self._map(connection, row) for row in connection.execute(sql, parameters).fetchall()]  # type: ignore[misc]
        return self.database.read(select)

    @staticmethod
    def _values(task: Task, now: str) -> tuple[object, ...]:
        return (
            task.title.strip(), task.description.strip(), str(task.status), str(task.priority), task.assignee_user_id,
            task.created_by, task.start_date.isoformat() if task.start_date else None,
            task.due_date.isoformat() if task.due_date else None, task.due_time.isoformat(timespec="minutes") if task.due_time else None,
            int(task.reminder_enabled), str(task.reminder_type) if task.reminder_type else None,
            to_storage(task.reminder_datetime), task.reminder_offset_minutes, to_storage(task.reminder_acknowledged_at),
            int(task.recurrence_enabled), str(task.recurrence_type) if task.recurrence_type else None,
            task.recurrence_interval, ",".join(str(day) for day in task.recurrence_weekdays), task.recurrence_day_of_month,
            task.recurrence_time.isoformat(timespec="minutes") if task.recurrence_time else None,
            to_storage(task.last_completed_at), to_storage(task.next_occurrence_at), now,
        )

    @staticmethod
    def _set_tags(connection: sqlite3.Connection, entity_id: int, tags: list[str], now: str) -> None:
        connection.execute("DELETE FROM entity_tags WHERE entity_type='task' AND entity_id=?", (entity_id,))
        for name in sorted({item.strip() for item in tags if item.strip()}, key=str.casefold):
            connection.execute("INSERT OR IGNORE INTO tags(name,created_at) VALUES(?,?)", (name, now))
            tag_id = connection.execute("SELECT id FROM tags WHERE name=? COLLATE NOCASE", (name,)).fetchone()[0]
            connection.execute("INSERT INTO entity_tags(entity_type,entity_id,tag_id) VALUES('task',?,?)", (entity_id, tag_id))

    def save(self, task: Task) -> Task:
        now = to_storage(self.clock.now())
        values = self._values(task, now)
        columns = ("title,description,status,priority,assignee_user_id,created_by,start_date,due_date,due_time,"
                   "reminder_enabled,reminder_type,reminder_datetime,reminder_offset_minutes,reminder_acknowledged_at,"
                   "recurrence_enabled,recurrence_type,recurrence_interval,recurrence_weekdays,recurrence_day_of_month,"
                   "recurrence_time,last_completed_at,next_occurrence_at,updated_at")
        if task.id is None:
            def insert(connection: sqlite3.Connection) -> int:
                cursor = connection.execute(
                    f"INSERT INTO tasks({columns},created_at) VALUES({','.join('?' for _ in range(24))})",
                    values + (now,),
                )
                entity_id = int(cursor.lastrowid)
                self._set_tags(connection, entity_id, task.tags, now or "")
                return entity_id
            task.id = self.database.write(insert)
        else:
            def update(connection: sqlite3.Connection) -> None:
                assignments = ",".join(f"{column}=?" for column in columns.split(","))
                connection.execute(f"UPDATE tasks SET {assignments} WHERE id=?", values + (task.id,))
                self._set_tags(connection, task.id or 0, task.tags, now or "")
            self.database.write(update)
        return self.find_by_id(task.id)  # type: ignore[arg-type,return-value]

    def delete(self, task_id: int) -> None:
        def remove(connection: sqlite3.Connection) -> None:
            connection.execute("DELETE FROM entity_tags WHERE entity_type='task' AND entity_id=?", (task_id,))
            connection.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        self.database.write(remove)

    def record_completion(self, task: Task, completed_by: int, scheduled_for: str | None) -> Task:
        now = to_storage(self.clock.now())
        values = self._values(task, now)
        columns = ("title,description,status,priority,assignee_user_id,created_by,start_date,due_date,due_time,"
                   "reminder_enabled,reminder_type,reminder_datetime,reminder_offset_minutes,reminder_acknowledged_at,"
                   "recurrence_enabled,recurrence_type,recurrence_interval,recurrence_weekdays,recurrence_day_of_month,"
                   "recurrence_time,last_completed_at,next_occurrence_at,updated_at")
        def complete(connection: sqlite3.Connection) -> None:
            assignments = ",".join(f"{column}=?" for column in columns.split(","))
            connection.execute(f"UPDATE tasks SET {assignments} WHERE id=?", values + (task.id,))
            self._set_tags(connection, task.id or 0, task.tags, now or "")
            connection.execute(
                "INSERT INTO task_completions(task_id,completed_by,scheduled_for,completed_at) VALUES(?,?,?,?)",
                (task.id, completed_by, scheduled_for, now),
            )
        self.database.write(complete)
        return self.find_by_id(task.id or 0)  # type: ignore[return-value]

    def completion_history(self, limit: int = 200) -> list[dict[str, object]]:
        return self.database.read(lambda connection: [dict(row) for row in connection.execute(
            "SELECT c.*,t.title,u.display_name FROM task_completions c "
            "JOIN tasks t ON t.id=c.task_id JOIN users u ON u.id=c.completed_by "
            "ORDER BY c.completed_at DESC LIMIT ?", (limit,)
        ).fetchall()])
