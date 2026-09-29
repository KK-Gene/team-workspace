from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from workspace.clock import FixedClock
from workspace.database import Database
from workspace.services import AppServices


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 10, 2, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


@pytest.fixture
def services(tmp_path, now):
    database = Database(tmp_path / "workspace.db")
    assert database.migrate() == 2
    services = AppServices(database, FixedClock(now), tmp_path / "backups", "Asia/Tokyo", 3)
    return services


@pytest.fixture
def user(services):
    return services.user_service.add_user("tester", "Test User", role="Admin")
