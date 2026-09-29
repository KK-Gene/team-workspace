from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar

from workspace.errors import DatabaseBusyError, MigrationError


T = TypeVar("T")
LOGGER = logging.getLogger("team_workspace.database")
LOCK_MESSAGES = ("database is locked", "database table is locked", "database schema is locked")


class Database:
    def __init__(self, path: Path, migration_dir: Path | None = None) -> None:
        self.path = Path(path)
        self.migration_dir = migration_dir or Path(__file__).resolve().parent.parent / "database" / "migrations"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5, detect_types=sqlite3.PARSE_DECLTYPES)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    def read(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        with self.connection() as connection:
            return operation(connection)

    def write(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        delays = (0.0, 0.1, 0.3, 0.7, 1.5)
        for attempt, delay in enumerate(delays, start=1):
            if delay:
                time.sleep(delay)
            try:
                with self.connection() as connection:
                    with connection:
                        return operation(connection)
            except sqlite3.OperationalError as exc:
                if not any(message in str(exc).lower() for message in LOCK_MESSAGES):
                    raise
                LOGGER.warning("Database lock retry %s/%s: %s", attempt, len(delays), exc)
                if attempt == len(delays):
                    raise DatabaseBusyError(
                        "データベースが使用中です。OneDriveの同期完了後にもう一度お試しください。"
                    ) from exc
        raise AssertionError("unreachable")

    def migrate(self) -> int:
        try:
            with self.connection() as connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS schema_version ("
                    "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, description TEXT)"
                )
                current = connection.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()[0]
            migrations = sorted(self.migration_dir.glob("[0-9][0-9][0-9]_*.sql"))
            available = max((int(item.name.split("_", 1)[0]) for item in migrations), default=0)
            if current > available:
                raise MigrationError(
                    f"データベースのスキーマ({current})がアプリの対応バージョン({available})より新しいため起動できません。"
                )
            for migration in migrations:
                version = int(migration.name.split("_", 1)[0])
                if version <= current:
                    continue
                sql = migration.read_text(encoding="utf-8")
                description = migration.stem.split("_", 1)[1]

                def apply(connection: sqlite3.Connection) -> None:
                    connection.executescript(sql)
                    connection.execute(
                        "INSERT INTO schema_version(version, applied_at, description) "
                        "VALUES (?, datetime('now'), ?)",
                        (version, description),
                    )

                self.write(apply)
                current = version
                LOGGER.info("Applied database migration %s", migration.name)
            return current
        except Exception as exc:
            LOGGER.exception("Database migration failed")
            if isinstance(exc, (DatabaseBusyError, MigrationError)):
                raise
            raise MigrationError("データベースの更新に失敗しました。ログを確認してください。") from exc

    def has_pending_migrations(self) -> bool:
        migrations = sorted(self.migration_dir.glob("[0-9][0-9][0-9]_*.sql"))
        available = max((int(item.name.split("_", 1)[0]) for item in migrations), default=0)
        def current_version(connection: sqlite3.Connection) -> int:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'"
            ).fetchone()
            if not exists:
                return 0
            return int(connection.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()[0])
        return self.read(current_version) < available

    def schema_version(self) -> int:
        return self.read(
            lambda connection: connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_version"
            ).fetchone()[0]
        )

    def integrity_check(self) -> str:
        result = self.read(lambda connection: connection.execute("PRAGMA integrity_check").fetchone()[0])
        if result != "ok":
            LOGGER.error("Integrity check failed: %s", result)
        else:
            LOGGER.info("Integrity check passed")
        return str(result)

    def journal_mode(self) -> str:
        return str(self.read(lambda connection: connection.execute("PRAGMA journal_mode").fetchone()[0]))
