from __future__ import annotations

import streamlit as st

from views.common import run_action
from workspace.models import User
from workspace.services import AppServices


def render(services: AppServices, user: User, settings) -> None:
    st.title("Settings")
    st.subheader("Current User")
    st.write(f"**{user.display_name}** (`{user.username}`) · {user.role}")

    st.subheader("Power Automate / Teams")
    summary = services.notification_outbox.summary()
    notification_cols = st.columns(4)
    notification_cols[0].metric("Connection", "Configured" if services.reminder_sync.configured else "Not configured")
    notification_cols[1].metric("Pending", summary["Pending"])
    notification_cols[2].metric("Sent", summary["Sent"])
    notification_cols[3].metric("Failed", summary["Failed"])
    st.caption(f"Delivery mode: {settings.notification_mode} · Webhook URLは環境変数から読み込み、画面やDBには表示しません。")
    if not services.reminder_sync.configured:
        st.info("TEAM_WORKSPACE_POWER_AUTOMATE_WEBHOOK_URL を各PCのローカル環境変数へ設定して再起動してください。")
    action_columns = st.columns(3)
    if action_columns[0].button("テスト通知を送信", disabled=not services.reminder_sync.configured, use_container_width=True):
        services.reminder_sync.queue_test(user)
        sent, failed = services.reminder_sync.flush()
        if sent:
            st.success("Power Automateへテスト通知を送信しました。")
        else:
            st.error(f"テスト通知を送信できませんでした。失敗: {failed}")
        st.rerun()
    if action_columns[1].button("全リマインダー同期", disabled=not services.reminder_sync.configured, use_container_width=True):
        queued = services.reminder_sync.resync_tasks(services.tasks.list())
        sent, failed = services.reminder_sync.flush()
        st.success(f"{queued}件を同期対象にし、{sent}件送信しました。失敗: {failed}")
        st.rerun()
    if action_columns[2].button("失敗通知を再送", disabled=not services.reminder_sync.configured, use_container_width=True):
        reset = services.notification_outbox.retry_failed()
        sent, failed = services.reminder_sync.flush()
        st.success(f"{reset}件を再試行対象に戻し、{sent}件送信しました。失敗: {failed}")
        st.rerun()
    with st.expander("通知同期履歴"):
        recent = services.notification_outbox.recent()
        if recent:
            st.dataframe(recent, use_container_width=True, hide_index=True)
        else:
            st.caption("通知イベントはまだありません。")

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
        all_users = services.users.list_all()
        selected_user_id = st.selectbox(
            "編集するユーザー",
            [item.id for item in all_users],
            format_func=lambda value: next(item.display_name for item in all_users if item.id == value),
        )
        selected_user = next(item for item in all_users if item.id == selected_user_id)
        with st.form(f"edit_user_{selected_user_id}"):
            edit_display_name = st.text_input("表示名", value=selected_user.display_name)
            edit_email = st.text_input("Teams用メールアドレス", value=selected_user.email or "")
            edit_role = st.selectbox("権限", ["Member", "Admin"], index=1 if selected_user.role == "Admin" else 0)
            edit_active = st.checkbox("有効", value=selected_user.active)
            if st.form_submit_button("ユーザー更新"):
                if run_action(
                    lambda: services.user_service.update_user(
                        selected_user_id, edit_display_name, edit_email, edit_role, edit_active
                    ),
                    "ユーザーを更新しました。",
                ):
                    st.rerun()
