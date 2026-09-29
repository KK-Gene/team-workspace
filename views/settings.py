from __future__ import annotations

import streamlit as st

from views.common import run_action
from workspace.models import User
from workspace.services import AppServices


def render(services: AppServices, user: User, settings) -> None:
    st.title("Settings")
    st.subheader("Current User")
    st.write(f"**{user.display_name}** (`{user.username}`) · {user.role}")

    st.subheader("Database Health")
    path = settings.database_path
    latest = services.backups.latest()
    cols = st.columns(4)
    cols[0].metric("Schema", services.database.schema_version())
    cols[1].metric("Size", f"{path.stat().st_size / 1024:.1f} KB" if path.exists() else "-")
    cols[2].metric("Journal", services.database.journal_mode())
    cols[3].metric("Last Backup", latest.name if latest else "なし")
    if st.button("整合性チェック"):
        result = services.database.integrity_check()
        st.success("正常です。" if result == "ok" else f"問題を検出: {result}")
    if st.button("今すぐバックアップ"):
        if run_action(services.backups.create, "バックアップを作成しました。"):
            st.rerun()
    st.warning("OneDrive はデータベースサーバーではありません。同時書き込みを避け、競合コピーが発生した場合は編集を止めて復旧手順に従ってください。")

    st.subheader("CSV Export")
    columns = st.columns(5)
    for column, name in zip(columns, services.exports.TABLES):
        column.download_button(
            name.capitalize(), services.exports.csv_bytes(name), file_name=f"{name}.csv", mime="text/csv",
            use_container_width=True,
        )

    st.subheader("Users")
    st.dataframe([{
        "ID": item.id, "Username": item.username, "Display Name": item.display_name,
        "Role": item.role, "Active": item.active,
    } for item in services.users.list_all()], use_container_width=True, hide_index=True)
    if user.role == "Admin":
        with st.form("add_user"):
            username = st.text_input("Windows username")
            display_name = st.text_input("Display name")
            email = st.text_input("Email (optional)")
            role = st.selectbox("Role", ["Member", "Admin"])
            if st.form_submit_button("ユーザー追加"):
                if run_action(lambda: services.user_service.add_user(username, display_name, email, role), "ユーザーを追加しました。"):
                    st.rerun()
