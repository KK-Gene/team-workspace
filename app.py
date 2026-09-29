from __future__ import annotations

import logging

import streamlit as st

from views import activity, dashboard, favorites, knowledge, settings as settings_view, tasks
from workspace.clock import SystemClock
from workspace.config import Settings
from workspace.database import Database
from workspace.errors import WorkspaceError
from workspace.logging_config import configure_logging
from workspace.services import AppServices, BackupService


st.set_page_config(page_title="Team Workspace", page_icon="🧭", layout="wide")


@st.cache_resource
def bootstrap() -> tuple[Settings, AppServices]:
    settings = Settings.from_environment()
    settings.ensure_directories()
    configure_logging(settings.log_path)
    clock = SystemClock(settings.timezone)
    database = Database(settings.database_path)
    database_existed = settings.database_path.exists() and settings.database_path.stat().st_size > 0
    if database_existed and database.has_pending_migrations():
        BackupService(database, settings.backup_dir, clock, settings.backup_retention).create()
    database.migrate()
    services = AppServices(database, clock, settings.backup_dir, settings.timezone, settings.backup_retention)
    try:
        services.backups.create_if_due(settings.backup_interval_hours)
    except Exception:
        logging.getLogger("team_workspace").exception("Automatic backup failed")
    return settings, services


try:
    app_settings, app_services = bootstrap()
    current_user = app_services.user_service.current_user()
except WorkspaceError as exc:
    st.error(str(exc)); st.stop()
except Exception:
    st.error("Team Workspace を起動できませんでした。logs/workspace.log を確認してください。"); st.stop()


with st.sidebar:
    st.title("🧭 Team Workspace")
    st.caption(f"{current_user.display_name} · {current_user.role}")
    search_query = st.text_input("横断検索", placeholder="タスク・知識を検索")
    if search_query.strip():
        results = app_services.search.search(search_query)
        st.caption(f"{len(results)} 件")
        for result in results[:15]:
            st.write(f"**{result['title']}**")
            st.caption(result["entity_type"])
    page = st.radio(
        "Navigation",
        ["Dashboard", "Tasks", "Snippets", "Links", "Glossary", "Notes", "Favorites", "Activity", "Settings"],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("SQLite + OneDrive MVP")


if page == "Dashboard": dashboard.render(app_services, current_user)
elif page == "Tasks": tasks.render(app_services, current_user)
elif page == "Snippets": knowledge.render(app_services, current_user, "snippet")
elif page == "Links": knowledge.render(app_services, current_user, "link")
elif page == "Glossary": knowledge.render(app_services, current_user, "glossary")
elif page == "Notes": knowledge.render(app_services, current_user, "note")
elif page == "Favorites": favorites.render(app_services, current_user)
elif page == "Activity": activity.render(app_services, current_user)
else: settings_view.render(app_services, current_user, app_settings)
