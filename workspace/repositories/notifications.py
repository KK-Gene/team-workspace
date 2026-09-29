from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from typing import Any

from workspace.clock import Clock, to_storage
from workspace.database import Database


class NotificationOutboxRepository:
    def __init__(self, database: Database, clock: Clock) -> None:
        self.database = database
        self.clock = clock

    def enqueue(
        self,
        event_id: str,
        notification_key: str,
        action: str,
        payload: dict[str, Any],
    ) -> int:
        now = to_storage(self.clock.now()) or ""
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

        def insert(connection: sqlite3.Connection) -> int:
            connection.execute(
                "UPDATE notification_outbox SET status='Superseded',updated_at=? "
                "WHERE notification_key=? AND status='Pending'",
                (now, notification_key),
            )
            cursor = connection.execute(
                "INSERT INTO notification_outbox("
                "event_id,notification_key,action,payload_json,status,attempts,next_attempt_at,created_at,updated_at"
                ") VALUES(?,?,?,?, 'Pending',0,?,?,?)",
                (event_id, notification_key, action, body, now, now, now),
            )
            return int(cursor.lastrowid)

        return self.database.write(insert)

    def pending(self, limit: int = 25) -> list[dict[str, Any]]:
        now = to_storage(self.clock.now()) or ""
        return self.database.read(lambda connection: [dict(row) for row in connection.execute(
            "SELECT * FROM notification_outbox WHERE status='Pending' "
            "AND (next_attempt_at IS NULL OR next_attempt_at<=?) "
            "ORDER BY created_at,id LIMIT ?",
            (now, limit),
        ).fetchall()])

    def mark_sent(self, row_id: int) -> None:
        now = to_storage(self.clock.now()) or ""
        self.database.write(lambda connection: connection.execute(
            "UPDATE notification_outbox SET status='Sent',sent_at=?,last_error='',updated_at=? WHERE id=?",
            (now, now, row_id),
        ))

    def mark_failure(self, row_id: int, attempts: int, error: str, max_attempts: int = 5) -> None:
        now_value = self.clock.now()
        status = "Failed" if attempts >= max_attempts else "Pending"
        delay_minutes = min(60, 2 ** max(0, attempts - 1))
        next_attempt = to_storage(now_value + timedelta(minutes=delay_minutes))
        self.database.write(lambda connection: connection.execute(
            "UPDATE notification_outbox SET status=?,attempts=?,next_attempt_at=?,last_error=?,updated_at=? WHERE id=?",
            (status, attempts, next_attempt, error[:500], to_storage(now_value), row_id),
        ))

    def retry_failed(self) -> int:
        now = to_storage(self.clock.now()) or ""
        def update(connection: sqlite3.Connection) -> int:
            cursor = connection.execute(
                "UPDATE notification_outbox SET status='Pending',attempts=0,next_attempt_at=?,last_error='',updated_at=? "
                "WHERE status='Failed'",
                (now, now),
            )
            return cursor.rowcount
        return self.database.write(update)

    def summary(self) -> dict[str, int]:
        rows = self.database.read(lambda connection: connection.execute(
            "SELECT status,COUNT(*) AS count FROM notification_outbox GROUP BY status"
        ).fetchall())
        result = {"Pending": 0, "Sent": 0, "Failed": 0, "Superseded": 0}
        result.update({str(row["status"]): int(row["count"]) for row in rows})
        return result

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.database.read(lambda connection: [dict(row) for row in connection.execute(
            "SELECT id,event_id,notification_key,action,status,attempts,sent_at,last_error,created_at,updated_at "
            "FROM notification_outbox ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()])

