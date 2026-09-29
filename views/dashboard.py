from __future__ import annotations

import streamlit as st

from views.common import task_rows
from workspace.models import TaskFilters, TaskStatus, User
from workspace.services import AppServices


def render(services: AppServices, user: User) -> None:
    st.title("Dashboard")
    st.caption(f"{user.display_name} さんの今日と、チーム全体の動きをまとめています。")
    my_day = services.tasks.my_day(user.id or 0)
    columns = st.columns(5)
    labels = [("期限超過", "overdue"), ("Critical", "critical"), ("通知", "reminders"), ("今日", "today"), ("繰り返し", "recurring")]
    for column, (label, key) in zip(columns, labels):
        column.metric(label, len(my_day[key]))

    user_names = {item.id or 0: item.display_name for item in services.users.list_all()}
    for title, key in (("🔴 期限超過", "overdue"), ("🔔 リマインダー", "reminders"), ("📅 今日のタスク", "today")):
        with st.expander(title, expanded=bool(my_day[key])):
            if my_day[key]:
                st.dataframe(task_rows(my_day[key], user_names), use_container_width=True, hide_index=True)
            else:
                st.caption("該当なし")

    left, right = st.columns(2)
    with left:
        st.subheader("Team Status")
        team = services.tasks.list(TaskFilters(statuses=[TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED]))
        if team:
            st.dataframe(task_rows(team, user_names), use_container_width=True, hide_index=True)
        else:
            st.caption("進行中・ブロック中のタスクはありません。")
    with right:
        st.subheader("Quick Access")
        favorites = services.favorites.list_for_user(user.id or 0)[:8]
        if favorites:
            for item in favorites:
                st.write(f"★ **{item['title']}** · {item['entity_type']}")
        else:
            st.caption("Favorite を登録するとここに表示されます。")

    st.subheader("Team Activity")
    activity = services.activity.list_recent(10)
    for item in activity:
        st.caption(f"{item['user_name']} {item['action']} {item['entity_type']}「{item['entity_title']}」")

