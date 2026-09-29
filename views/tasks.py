from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import streamlit as st

from views.common import run_action, task_label, task_rows
from workspace.models import Priority, RecurrenceType, ReminderType, Task, TaskFilters, TaskStatus, User
from workspace.services import AppServices, parse_tags


STATUS_OPTIONS = [item.value for item in TaskStatus]
PRIORITY_OPTIONS = [item.value for item in Priority]


def _task_form(services: AppServices, user: User, existing: Task | None) -> None:
    users = services.users.list_active()
    user_options = {"未割当": None, **{item.display_name: item.id for item in users}}
    title = "タスク編集" if existing else "クイック追加"
    with st.expander(title, expanded=existing is not None):
        with st.form(f"task_form_{existing.id if existing else 'new'}"):
            task_title = st.text_input("タイトル *", value=existing.title if existing else "")
            labels = list(user_options)
            current_assignee = existing.assignee_user_id if existing else user.id
            selected_label = next((label for label, value in user_options.items() if value == current_assignee), "未割当")
            assignee = user_options[st.selectbox("担当", labels, index=labels.index(selected_label))]
            due_enabled = st.checkbox("期限を設定", value=bool(existing and existing.due_date))
            due_date = st.date_input("期限日", value=existing.due_date if existing and existing.due_date else services.clock.now().date(), disabled=not due_enabled)
            due_time_enabled = st.checkbox("期限時刻を設定", value=bool(existing and existing.due_time), disabled=not due_enabled)
            due_time = st.time_input("期限時刻", value=existing.due_time if existing and existing.due_time else time(17), disabled=not due_time_enabled)

            with st.expander("詳細設定"):
                description = st.text_area("説明", value=existing.description if existing else "")
                status = st.selectbox("ステータス", STATUS_OPTIONS, index=STATUS_OPTIONS.index(str(existing.status)) if existing else 1)
                priority = st.selectbox("優先度", PRIORITY_OPTIONS, index=PRIORITY_OPTIONS.index(str(existing.priority)) if existing else 1)
                start_enabled = st.checkbox("開始日を設定", value=bool(existing and existing.start_date))
                start_date = st.date_input("開始日", value=existing.start_date if existing and existing.start_date else services.clock.now().date(), disabled=not start_enabled)
                tags = st.text_input("タグ（カンマ区切り）", value=", ".join(existing.tags) if existing else "")

                reminder_enabled = st.checkbox("リマインダー", value=bool(existing and existing.reminder_enabled))
                reminder_type = st.radio("通知方式", [ReminderType.RELATIVE.value, ReminderType.ABSOLUTE.value],
                                         horizontal=True, disabled=not reminder_enabled,
                                         index=1 if existing and existing.reminder_type == ReminderType.ABSOLUTE else 0)
                offset_choices = {"10分前": 10, "30分前": 30, "1時間前": 60, "2時間前": 120, "1日前": 1440}
                current_offset = existing.reminder_offset_minutes if existing else 60
                offset_label = next((label for label, value in offset_choices.items() if value == current_offset), "1時間前")
                offset = offset_choices[st.selectbox("通知タイミング", list(offset_choices), index=list(offset_choices).index(offset_label),
                                                     disabled=not reminder_enabled or reminder_type != ReminderType.RELATIVE)]
                local_existing = existing.reminder_datetime if existing and existing.reminder_datetime else services.clock.now()
                reminder_date = st.date_input("通知日", value=local_existing.date(), disabled=not reminder_enabled or reminder_type != ReminderType.ABSOLUTE)
                reminder_time = st.time_input("通知時刻", value=local_existing.time().replace(second=0, microsecond=0),
                                              disabled=not reminder_enabled or reminder_type != ReminderType.ABSOLUTE)

                recurrence_enabled = st.checkbox("繰り返し", value=bool(existing and existing.recurrence_enabled))
                recurrence_types = [item.value for item in RecurrenceType]
                recurrence_type = st.selectbox("繰り返し種別", recurrence_types,
                                               index=recurrence_types.index(str(existing.recurrence_type)) if existing and existing.recurrence_type else 0,
                                               disabled=not recurrence_enabled)
                interval_label = "間隔（週）" if recurrence_type == RecurrenceType.INTERVAL else "間隔"
                interval = st.number_input(interval_label, min_value=1, max_value=365,
                                           value=existing.recurrence_interval if existing else 1, disabled=not recurrence_enabled)
                weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
                selected_weekdays = st.multiselect("曜日", weekday_names,
                    default=[weekday_names[index] for index in existing.recurrence_weekdays] if existing else [weekday_names[services.clock.now().weekday()]],
                    disabled=not recurrence_enabled or recurrence_type != RecurrenceType.WEEKLY)
                month_day = st.number_input("毎月の日", 1, 31,
                    value=existing.recurrence_day_of_month if existing and existing.recurrence_day_of_month else services.clock.now().day,
                    disabled=not recurrence_enabled or recurrence_type != RecurrenceType.MONTHLY)
                recurrence_time = st.time_input("実行時刻", value=existing.recurrence_time if existing and existing.recurrence_time else time(9), disabled=not recurrence_enabled)

            submitted = st.form_submit_button("保存", type="primary", use_container_width=True)
            if submitted:
                absolute_datetime = None
                if reminder_enabled and reminder_type == ReminderType.ABSOLUTE:
                    absolute_datetime = datetime.combine(reminder_date, reminder_time, ZoneInfo("Asia/Tokyo"))
                task = Task(
                    id=existing.id if existing else None,
                    title=task_title,
                    description=description,
                    status=status,
                    priority=priority,
                    assignee_user_id=assignee,
                    created_by=existing.created_by if existing else (user.id or 0),
                    start_date=start_date if start_enabled else None,
                    due_date=due_date if due_enabled else None,
                    due_time=due_time if due_enabled and due_time_enabled else None,
                    reminder_enabled=reminder_enabled,
                    reminder_type=reminder_type if reminder_enabled else None,
                    reminder_datetime=absolute_datetime,
                    reminder_offset_minutes=offset if reminder_enabled and reminder_type == ReminderType.RELATIVE else None,
                    reminder_acknowledged_at=existing.reminder_acknowledged_at if existing else None,
                    recurrence_enabled=recurrence_enabled,
                    recurrence_type=recurrence_type if recurrence_enabled else None,
                    recurrence_interval=int(interval),
                    recurrence_weekdays=[weekday_names.index(name) for name in selected_weekdays],
                    recurrence_day_of_month=int(month_day) if recurrence_enabled and recurrence_type == RecurrenceType.MONTHLY else None,
                    recurrence_time=recurrence_time if recurrence_enabled else None,
                    last_completed_at=existing.last_completed_at if existing else None,
                    next_occurrence_at=existing.next_occurrence_at if existing else None,
                    tags=parse_tags(tags),
                )
                if run_action(lambda: services.tasks.save(task, user.id or 0), "タスクを保存しました。"):
                    st.session_state.pop("edit_task_id", None)
                    st.rerun()


def render(services: AppServices, user: User) -> None:
    st.title("Tasks")
    edit_id = st.session_state.get("edit_task_id")
    existing = services.tasks.get(edit_id) if edit_id else None
    _task_form(services, user, existing)

    st.subheader("タスク一覧")
    users = services.users.list_all()
    user_names = {item.id or 0: item.display_name for item in users}
    col1, col2, col3, col4 = st.columns(4)
    view = col1.selectbox("ビュー", ["My Tasks", "Team Tasks", "Today", "Upcoming", "Recurring", "Completed"])
    statuses = col2.multiselect("ステータス", STATUS_OPTIONS, default=[])
    priorities = col3.multiselect("優先度", PRIORITY_OPTIONS, default=[])
    text = col4.text_input("検索")
    if view == "Completed":
        history = services.tasks_repo.completion_history()
        st.dataframe(history, use_container_width=True, hide_index=True)
        return
    filters = TaskFilters(statuses=statuses, priorities=priorities, text=text or None)
    if view == "My Tasks": filters.assignee_user_id = user.id
    if view == "Today": filters.due_from = filters.due_to = services.clock.now().date()
    if view == "Upcoming": filters.due_from = services.clock.now().date()
    if view == "Recurring": filters.recurring_only = True
    tasks = services.tasks.list(filters)
    st.dataframe(task_rows(tasks, user_names), use_container_width=True, hide_index=True)

    if tasks:
        selected_id = st.selectbox("操作するタスク", [task.id for task in tasks], format_func=lambda value: task_label(next(task for task in tasks if task.id == value)))
        selected = next(task for task in tasks if task.id == selected_id)
        buttons = st.columns(4)
        if buttons[0].button("編集", use_container_width=True):
            st.session_state["edit_task_id"] = selected.id; st.rerun()
        if buttons[1].button("完了", type="primary", use_container_width=True, disabled=selected.status == TaskStatus.DONE):
            if run_action(lambda: services.tasks.complete(selected.id or 0, user.id or 0), "タスクを完了しました。"):
                st.rerun()
        if buttons[2].button("通知確認済み", use_container_width=True, disabled=not services.reminders.is_due(selected)):
            if run_action(lambda: services.tasks.acknowledge_reminder(selected.id or 0, user.id or 0), "リマインダーを確認済みにしました。"):
                st.rerun()
        confirm = buttons[3].checkbox("削除確認", key=f"confirm_task_{selected.id}")
        if st.button("選択タスクを削除", disabled=not confirm):
            if run_action(lambda: services.tasks.delete(selected.id or 0, user.id or 0), "タスクを削除しました。"):
                st.rerun()
