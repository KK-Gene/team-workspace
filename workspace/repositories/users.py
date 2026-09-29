from __future__ import annotations

import sqlite3

from workspace.clock import Clock, from_storage, to_storage
from workspace.database import Database
from workspace.models import User


class UserRepository:
    def __init__(self, database: Database, clock: Clock) -> None:
        self.database = database
        self.clock = clock

    @staticmethod
    def _map(row: sqlite3.Row | None) -> User | None:
        if row is None:
            return None
        return User(
            id=row["id"], username=row["username"], display_name=row["display_name"],
            email=row["email"], role=row["role"], active=bool(row["active"]),
            created_at=from_storage(row["created_at"]), updated_at=from_storage(row["updated_at"]),
        )

    def find_by_username(self, username: str) -> User | None:
        return self.database.read(
            lambda connection: self._map(
                connection.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
            )
        )

    def find_by_id(self, user_id: int) -> User | None:
        return self.database.read(
            lambda connection: self._map(connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())
        )

    def list_active(self) -> list[User]:
        return self.database.read(
            lambda connection: [self._map(row) for row in connection.execute(
                "SELECT * FROM users WHERE active = 1 ORDER BY display_name COLLATE NOCASE"
            ).fetchall()]
        )  # type: ignore[list-item]

    def list_all(self) -> list[User]:
        return self.database.read(
            lambda connection: [self._map(row) for row in connection.execute(
                "SELECT * FROM users ORDER BY display_name COLLATE NOCASE"
            ).fetchall()]
        )  # type: ignore[list-item]

    def save(self, user: User) -> User:
        now = to_storage(self.clock.now())
        if user.id is None:
            def insert(connection: sqlite3.Connection) -> int:
                cursor = connection.execute(
                    "INSERT INTO users(username,display_name,email,role,active,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (user.username.strip(), user.display_name.strip(), user.email, user.role, int(user.active), now, now),
                )
                return int(cursor.lastrowid)
            user.id = self.database.write(insert)
        else:
            self.database.write(lambda connection: connection.execute(
                "UPDATE users SET username=?,display_name=?,email=?,role=?,active=?,updated_at=? WHERE id=?",
                (user.username.strip(), user.display_name.strip(), user.email, user.role, int(user.active), now, user.id),
            ))
        return self.find_by_id(user.id)  # type: ignore[arg-type,return-value]

