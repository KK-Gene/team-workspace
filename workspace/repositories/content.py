from __future__ import annotations

import sqlite3
from typing import Any

from workspace.clock import Clock, to_storage
from workspace.database import Database


ENTITY_CONFIG: dict[str, tuple[str, list[str], str]] = {
    "snippet": ("snippets", ["title", "description", "content", "language", "category"], "title"),
    "link": ("links", ["title", "url", "description", "category"], "title"),
    "glossary": ("glossary_entries", ["term", "abbreviation", "definition", "category", "related_terms", "related_links"], "term"),
    "note": ("notes", ["title", "content", "category"], "title"),
}


class ContentRepository:
    def __init__(self, database: Database, clock: Clock, entity_type: str) -> None:
        if entity_type not in ENTITY_CONFIG:
            raise ValueError(f"Unsupported entity type: {entity_type}")
        self.database = database
        self.clock = clock
        self.entity_type = entity_type
        self.table, self.fields, self.title_field = ENTITY_CONFIG[entity_type]

    def _tags(self, connection: sqlite3.Connection, entity_id: int) -> list[str]:
        return [row[0] for row in connection.execute(
            "SELECT t.name FROM tags t JOIN entity_tags et ON et.tag_id=t.id "
            "WHERE et.entity_type=? AND et.entity_id=? ORDER BY t.name",
            (self.entity_type, entity_id),
        ).fetchall()]

    def _map(self, connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["tags"] = self._tags(connection, item["id"])
        return item

    def find_by_id(self, entity_id: int) -> dict[str, Any] | None:
        def select(connection: sqlite3.Connection) -> dict[str, Any] | None:
            row = connection.execute(f"SELECT * FROM {self.table} WHERE id=?", (entity_id,)).fetchone()
            return self._map(connection, row) if row else None
        return self.database.read(select)

    def find_all(self, text: str = "", category: str = "", tag: str = "") -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[object] = []
        if text:
            search_fields = self.fields
            clauses.append("(" + " OR ".join(f"{field} LIKE ?" for field in search_fields) + ")")
            params.extend([f"%{text}%"] * len(search_fields))
        if category:
            clauses.append("category=?"); params.append(category)
        if tag:
            clauses.append("EXISTS(SELECT 1 FROM entity_tags et JOIN tags t ON t.id=et.tag_id "
                           f"WHERE et.entity_type=? AND et.entity_id={self.table}.id AND t.name=? COLLATE NOCASE)")
            params.extend((self.entity_type, tag))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        order = self.title_field + " COLLATE NOCASE" if self.entity_type == "glossary" else "updated_at DESC"
        sql = f"SELECT * FROM {self.table}{where} ORDER BY {order}"
        return self.database.read(
            lambda connection: [self._map(connection, row) for row in connection.execute(sql, params).fetchall()]
        )

    def categories(self) -> list[str]:
        return self.database.read(lambda connection: [row[0] for row in connection.execute(
            f"SELECT DISTINCT category FROM {self.table} WHERE category<>'' ORDER BY category COLLATE NOCASE"
        ).fetchall()])

    def _set_tags(self, connection: sqlite3.Connection, entity_id: int, tags: list[str], now: str) -> None:
        connection.execute("DELETE FROM entity_tags WHERE entity_type=? AND entity_id=?", (self.entity_type, entity_id))
        for name in sorted({tag.strip() for tag in tags if tag.strip()}, key=str.casefold):
            connection.execute("INSERT OR IGNORE INTO tags(name,created_at) VALUES(?,?)", (name, now))
            tag_id = connection.execute("SELECT id FROM tags WHERE name=? COLLATE NOCASE", (name,)).fetchone()[0]
            connection.execute(
                "INSERT INTO entity_tags(entity_type,entity_id,tag_id) VALUES(?,?,?)",
                (self.entity_type, entity_id, tag_id),
            )

    def save(self, values: dict[str, Any], entity_id: int | None = None) -> dict[str, Any]:
        now = to_storage(self.clock.now()) or ""
        normalized = [str(values.get(field, "") or "").strip() for field in self.fields]
        created_by = int(values["created_by"])
        tags = list(values.get("tags", []))
        extra_fields: list[str] = []
        extra_values: list[object] = []
        if self.entity_type == "snippet" and entity_id is None:
            extra_fields.append("usage_count"); extra_values.append(0)
        if entity_id is None:
            fields = self.fields + ["created_by", "created_at", "updated_at"] + extra_fields
            params = normalized + [created_by, now, now] + extra_values
            def insert(connection: sqlite3.Connection) -> int:
                cursor = connection.execute(
                    f"INSERT INTO {self.table}({','.join(fields)}) VALUES({','.join('?' for _ in fields)})", params
                )
                new_id = int(cursor.lastrowid)
                self._set_tags(connection, new_id, tags, now)
                return new_id
            entity_id = self.database.write(insert)
        else:
            def update(connection: sqlite3.Connection) -> None:
                assignments = ",".join(f"{field}=?" for field in self.fields)
                connection.execute(
                    f"UPDATE {self.table} SET {assignments},updated_at=? WHERE id=?",
                    normalized + [now, entity_id],
                )
                self._set_tags(connection, entity_id or 0, tags, now)
            self.database.write(update)
        return self.find_by_id(entity_id) or {}

    def delete(self, entity_id: int) -> None:
        def remove(connection: sqlite3.Connection) -> None:
            connection.execute("DELETE FROM entity_tags WHERE entity_type=? AND entity_id=?", (self.entity_type, entity_id))
            connection.execute("DELETE FROM favorites WHERE entity_type=? AND entity_id=?", (self.entity_type, entity_id))
            connection.execute(f"DELETE FROM {self.table} WHERE id=?", (entity_id,))
        self.database.write(remove)

    def increment_usage(self, entity_id: int) -> None:
        if self.entity_type == "snippet":
            self.database.write(lambda connection: connection.execute(
                "UPDATE snippets SET usage_count=usage_count+1 WHERE id=?", (entity_id,)
            ))


class ActivityRepository:
    def __init__(self, database: Database, clock: Clock) -> None:
        self.database = database
        self.clock = clock

    def add(self, user_id: int | None, action: str, entity_type: str, entity_id: int | None,
            title: str, details: str = "") -> None:
        self.database.write(lambda connection: connection.execute(
            "INSERT INTO activity_log(user_id,action,entity_type,entity_id,entity_title,details,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (user_id, action, entity_type, entity_id, title, details, to_storage(self.clock.now())),
        ))

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.database.read(lambda connection: [dict(row) for row in connection.execute(
            "SELECT a.*,COALESCE(u.display_name,'Unknown') AS user_name FROM activity_log a "
            "LEFT JOIN users u ON u.id=a.user_id ORDER BY a.created_at DESC LIMIT ?", (limit,)
        ).fetchall()])


class FavoriteRepository:
    def __init__(self, database: Database, clock: Clock) -> None:
        self.database = database
        self.clock = clock

    def toggle(self, user_id: int, entity_type: str, entity_id: int) -> bool:
        def mutate(connection: sqlite3.Connection) -> bool:
            existing = connection.execute(
                "SELECT id FROM favorites WHERE user_id=? AND entity_type=? AND entity_id=?",
                (user_id, entity_type, entity_id),
            ).fetchone()
            if existing:
                connection.execute("DELETE FROM favorites WHERE id=?", (existing[0],))
                return False
            connection.execute(
                "INSERT INTO favorites(user_id,entity_type,entity_id,created_at) VALUES(?,?,?,?)",
                (user_id, entity_type, entity_id, to_storage(self.clock.now())),
            )
            return True
        return self.database.write(mutate)

    def is_favorite(self, user_id: int, entity_type: str, entity_id: int) -> bool:
        return self.database.read(lambda connection: connection.execute(
            "SELECT 1 FROM favorites WHERE user_id=? AND entity_type=? AND entity_id=?",
            (user_id, entity_type, entity_id),
        ).fetchone() is not None)

    def list_for_user(self, user_id: int) -> list[dict[str, Any]]:
        def select(connection: sqlite3.Connection) -> list[dict[str, Any]]:
            results: list[dict[str, Any]] = []
            for entity_type, (table, _, title_field) in ENTITY_CONFIG.items():
                rows = connection.execute(
                    f"SELECT f.entity_type,f.entity_id,f.created_at,e.{title_field} AS title "
                    f"FROM favorites f JOIN {table} e ON e.id=f.entity_id "
                    "WHERE f.user_id=? AND f.entity_type=? ORDER BY f.created_at DESC",
                    (user_id, entity_type),
                ).fetchall()
                results.extend(dict(row) for row in rows)
            return sorted(results, key=lambda item: str(item["created_at"]), reverse=True)
        return self.database.read(select)

