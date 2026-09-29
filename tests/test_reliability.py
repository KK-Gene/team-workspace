import sqlite3


def test_migration_and_integrity(services):
    assert services.database.schema_version() == 1
    assert services.database.integrity_check() == "ok"


def test_backup_and_retention(services, user):
    services.user_service.add_user("second", "Second")
    backup = services.backups.create()
    assert backup.exists()
    with sqlite3.connect(backup) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 2


def test_csv_export(services, user):
    services.tasks.save(__import__("workspace.models", fromlist=["Task"]).Task(title="Export me", created_by=user.id), user.id)
    data = services.exports.csv_bytes("tasks").decode("utf-8-sig")
    assert "title" in data
    assert "Export me" in data
