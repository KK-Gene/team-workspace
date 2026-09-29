from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True, slots=True)
class Settings:
    root_dir: Path
    database_path: Path
    backup_dir: Path
    log_path: Path
    timezone: str = "Asia/Tokyo"
    backup_interval_hours: int = 24
    backup_retention: int = 15

    @classmethod
    def from_environment(cls) -> "Settings":
        db_value = os.getenv("TEAM_WORKSPACE_DB", "data/workspace.db")
        db_path = Path(db_value)
        if not db_path.is_absolute():
            db_path = ROOT_DIR / db_path
        return cls(
            root_dir=ROOT_DIR,
            database_path=db_path,
            backup_dir=ROOT_DIR / "backups",
            log_path=ROOT_DIR / "logs" / "workspace.log",
            timezone=os.getenv("TEAM_WORKSPACE_TIMEZONE", "Asia/Tokyo"),
            backup_interval_hours=int(os.getenv("TEAM_WORKSPACE_BACKUP_INTERVAL_HOURS", "24")),
            backup_retention=int(os.getenv("TEAM_WORKSPACE_BACKUP_RETENTION", "15")),
        )

    def ensure_directories(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

