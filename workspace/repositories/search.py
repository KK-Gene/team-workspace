from __future__ import annotations

from typing import Any

from workspace.database import Database


class SearchRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def search(self, query: str, limit_per_type: int = 20) -> list[dict[str, Any]]:
        pattern = f"%{query.strip()}%"
        prefix = f"{query.strip()}%"

        def select(connection):
            specs = [
                ("task", "tasks", "title", ["title", "description"]),
                ("snippet", "snippets", "title", ["title", "description", "content", "language", "category"]),
                ("link", "links", "title", ["title", "url", "description", "category"]),
                ("glossary", "glossary_entries", "term", ["term", "abbreviation", "definition", "related_terms"]),
                ("note", "notes", "title", ["title", "content", "category"]),
            ]
            results = []
            for entity_type, table, title, fields in specs:
                where = " OR ".join(f"{field} LIKE ?" for field in fields)
                sql = (
                    f"SELECT id,{title} AS title,updated_at,"
                    f"CASE WHEN {title}=? COLLATE NOCASE THEN 100 WHEN {title} LIKE ? THEN 80 ELSE 50 END AS score "
                    f"FROM {table} WHERE {where} ORDER BY score DESC,updated_at DESC LIMIT ?"
                )
                params = [query.strip(), prefix] + [pattern] * len(fields) + [limit_per_type]
                for row in connection.execute(sql, params).fetchall():
                    item = dict(row); item["entity_type"] = entity_type; results.append(item)
            return sorted(results, key=lambda item: (-item["score"], str(item["title"]).casefold()))
        return self.database.read(select)
