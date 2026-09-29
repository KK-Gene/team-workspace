from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from workspace.clock import SystemClock
from workspace.database import Database
from workspace.models import Priority, Task
from workspace.services import AppServices


def main() -> None:
    parser = argparse.ArgumentParser(description="Insert optional Team Workspace development data.")
    parser.add_argument("--database", required=True, type=Path, help="Explicit target database path")
    parser.add_argument("--confirm", action="store_true", help="Required safety acknowledgement")
    args = parser.parse_args()
    if not args.confirm:
        raise SystemExit("Refusing to seed without --confirm")
    database = Database(args.database.resolve())
    database.migrate()
    clock = SystemClock("Asia/Tokyo")
    services = AppServices(database, clock, args.database.resolve().parent / "backups", "Asia/Tokyo")
    if services.users.list_all():
        raise SystemExit("Refusing to seed a database that already contains users")
    admin = services.user_service.add_user("Admin", "Admin", role="Admin")
    member_a = services.user_service.add_user("MemberA", "Member A")
    member_b = services.user_service.add_user("MemberB", "Member B")
    for index, title in enumerate(("Weekly report", "Review specification", "Backup check", "Investigate test result", "Update runbook")):
        services.tasks.save(Task(
            title=title, created_by=admin.id or 0, assignee_user_id=[admin.id, member_a.id, member_b.id][index % 3],
            due_date=(clock.now() + timedelta(days=index)).date(), priority=Priority.HIGH if index == 0 else Priority.MEDIUM,
            tags=["sample"],
        ), admin.id or 0)
    services.content["snippet"].save({"title": "SQLite integrity check", "description": "Database health command",
        "content": "PRAGMA integrity_check;", "language": "sql", "category": "SQL", "tags": ["sqlite"]}, admin.id or 0)
    services.content["link"].save({"title": "Python Documentation", "url": "https://docs.python.org/3/",
        "description": "Official Python documentation", "category": "Development", "tags": ["python"]}, admin.id or 0)
    services.content["glossary"].save({"term": "MVP", "abbreviation": "MVP", "definition": "Minimum Viable Product",
        "category": "General", "related_terms": "", "related_links": "", "tags": ["onboarding"]}, admin.id or 0)
    services.content["note"].save({"title": "Welcome", "content": "# Team Workspace\n\nUse search before asking where information is.",
        "category": "Onboarding", "tags": ["onboarding"]}, admin.id or 0)
    print(f"Seeded development data into {args.database.resolve()}")


if __name__ == "__main__":
    main()
