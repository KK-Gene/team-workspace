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
        background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
        border-right: 1px solid #e2e8f0;
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
        color: #64748b;
    }
    [data-testid="stSidebarNav"] a[aria-current="page"] {
        background: #eef2ff;
        border: 1px solid #c7d2fe;
        border-radius: .65rem;
        color: #3730a3;
        font-weight: 650;
    }
    [data-testid="stSidebarNav"] a[aria-current="page"] span[data-testid="stIconMaterial"] {
        color: #4f46e5;
    }
    .tw-brand {
        display: flex;
        align-items: center;
        gap: .7rem;
        padding: .15rem .1rem .85rem;
    }
    .tw-brand-mark {
        display: grid;
        place-items: center;
        width: 2.25rem;
        height: 2.25rem;
        border-radius: .7rem;
        color: white;
        background: linear-gradient(135deg, #4f46e5, #7c3aed);
        box-shadow: 0 6px 16px rgba(79, 70, 229, .22);
        font-size: 1.15rem;
    }
    .tw-brand-name { color: #172033; font-size: 1.02rem; font-weight: 750; line-height: 1.1; }
    .tw-brand-sub { color: #64748b; font-size: .7rem; letter-spacing: .08em; margin-top: .22rem; }
    .tw-user {
        display: flex;
        align-items: center;
        gap: .65rem;
        margin: 0 0 .85rem;
        padding: .65rem .7rem;
        border: 1px solid #e2e8f0;
        border-radius: .7rem;
        background: rgba(255,255,255,.75);
    }
    .tw-avatar {
        display: grid;
        place-items: center;
        min-width: 1.9rem;
        height: 1.9rem;
        border-radius: 50%;
        color: #4338ca;
        background: #e0e7ff;
        font-size: .8rem;
        font-weight: 750;
    }
    .tw-user-name { color: #1e293b; font-size: .84rem; font-weight: 650; line-height: 1.1; }
    .tw-user-role { color: #64748b; font-size: .7rem; margin-top: .2rem; }
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
        '<div class="tw-brand"><div class="tw-brand-mark">◆</div>'
        '<div><div class="tw-brand-name">Team Workspace</div>'
        '<div class="tw-brand-sub">SHARED OPERATIONS</div></div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="tw-user"><div class="tw-avatar">{initials}</div><div>'
        f'<div class="tw-user-name">{current_user.display_name}</div>'
        f'<div class="tw-user-role">{current_user.role}</div></div></div>',
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
