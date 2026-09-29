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

st.markdown(
    """
    <style>
    [data-testid="stSidebar"] {
        background: #f7f7f8;
        border-right: 1px solid #e8e8eb;
    }
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 1.15rem;
    }
    [data-testid="stSidebarContent"] {
        display: flex;
        flex-direction: column;
    }
    [data-testid="stSidebarHeader"] { order: 0; }
    [data-testid="stSidebarUserContent"] {
        order: 1;
        padding: .15rem 1.25rem .65rem;
    }
    [data-testid="stSidebarNav"] { order: 2; }
    [data-testid="stSidebarNav"] {
        padding-top: .35rem;
    }
    [data-testid="stSidebarNavItems"] > header {
        margin: .25rem .65rem .05rem;
    }
    [data-testid="stSidebarNavItems"] > li {
        margin: .05rem .65rem;
    }
    [data-testid="stSidebarNav"] span[data-testid="stIconMaterial"] {
        color: #777780;
    }
    [data-testid="stSidebarNav"] a[aria-current="page"] {
        background: #e9e9ec;
        border: 1px solid transparent;
        border-radius: .65rem;
        color: #18181b;
        font-weight: 650;
    }
    [data-testid="stSidebarNav"] a[aria-current="page"] span[data-testid="stIconMaterial"] {
        color: #27272a;
    }
    [data-testid="stSidebarNavItems"] > header {
        color: #92929a;
        font-size: .7rem;
        font-weight: 520;
    }
    [data-testid="stSidebarUserContent"] [data-testid="stTextInput"] input {
        background: #eeeeef;
        border: 1px solid transparent;
        border-radius: .55rem;
        box-shadow: none;
        font-size: .8rem;
    }
    [data-testid="stSidebarUserContent"] [data-testid="stTextInput"] input:focus {
        background: white;
        border-color: #d4d4d8;
        box-shadow: 0 0 0 1px #d4d4d8;
    }
    .tw-workspace {
        display: flex;
        align-items: center;
        justify-content: space-between;
        min-height: 2.45rem;
        margin: 0 0 .55rem;
        padding: .28rem .35rem .28rem .4rem;
        border-radius: .55rem;
    }
    .tw-workspace:hover { background: #eeeeef; }
    .tw-workspace-name { color: #27272a; font-size: .86rem; font-weight: 640; line-height: 1.2; }
    .tw-workspace-meta { color: #8a8a92; font-size: .68rem; margin-top: .18rem; }
    .tw-avatar {
        display: grid;
        place-items: center;
        min-width: 1.55rem;
        height: 1.55rem;
        border-radius: .42rem;
        color: #52525b;
        background: #e4e4e7;
        font-size: .66rem;
        font-weight: 650;
    }
    .tw-result {
        padding: .42rem .55rem;
        margin: .28rem 0;
        border-radius: .5rem;
        background: white;
        border: 1px solid #e2e8f0;
        font-size: .8rem;
    }
    .tw-result-type { color: #64748b; font-size: .66rem; text-transform: uppercase; letter-spacing: .04em; }
    </style>
    """,
    unsafe_allow_html=True,
)


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
    initials = "".join(part[0].upper() for part in current_user.display_name.split()[:2]) or "U"
    st.markdown(
        '<div class="tw-workspace"><div>'
        '<div class="tw-workspace-name">Team Workspace</div>'
        f'<div class="tw-workspace-meta">{current_user.display_name} · {current_user.role}</div>'
        f'</div><div class="tw-avatar">{initials}</div></div>',
        unsafe_allow_html=True,
    )
    search_query = st.text_input("横断検索", placeholder="すべてを検索…", label_visibility="collapsed")
    if search_query.strip():
        results = app_services.search.search(search_query)
        st.caption(f"検索結果 · {len(results)}件")
        for result in results[:15]:
            st.markdown(
                f'<div class="tw-result"><div>{result["title"]}</div>'
                f'<div class="tw-result-type">{result["entity_type"]}</div></div>',
                unsafe_allow_html=True,
            )


pages = {
    "ホーム": [
        st.Page(lambda: dashboard.render(app_services, current_user), title="ダッシュボード", icon=":material/home:", url_path="dashboard", default=True),
    ],
    "仕事": [
        st.Page(lambda: tasks.render(app_services, current_user), title="タスク", icon=":material/check_circle:", url_path="tasks"),
    ],
    "ナレッジ": [
        st.Page(lambda: knowledge.render(app_services, current_user, "snippet"), title="スニペット", icon=":material/code:", url_path="snippets"),
        st.Page(lambda: knowledge.render(app_services, current_user, "glossary"), title="用語集", icon=":material/menu_book:", url_path="glossary"),
        st.Page(lambda: knowledge.render(app_services, current_user, "note"), title="ノート", icon=":material/description:", url_path="notes"),
    ],
    "リソース": [
        st.Page(lambda: knowledge.render(app_services, current_user, "link"), title="リンク", icon=":material/link:", url_path="links"),
    ],
    "個人": [
        st.Page(lambda: favorites.render(app_services, current_user), title="お気に入り", icon=":material/star:", url_path="favorites"),
    ],
    "システム": [
        st.Page(lambda: activity.render(app_services, current_user), title="アクティビティ", icon=":material/history:", url_path="activity"),
        st.Page(lambda: settings_view.render(app_services, current_user, app_settings), title="設定", icon=":material/settings:", url_path="settings"),
    ],
}

navigation = st.navigation(pages, position="sidebar")
navigation.run()
