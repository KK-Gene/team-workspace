from __future__ import annotations

from datetime import datetime, time
from html import escape
from zoneinfo import ZoneInfo

import streamlit as st

from views.common import format_timestamp, run_action
from views.task_components import (
    PRIORITY_LABELS,
    STATUS_LABELS,
    inject_task_styles,
    priority_slug,
    render_list_heading,
    render_task_header,
    render_task_stats,
    task_card_markup,
)
from workspace.models import Priority, RecurrenceType, ReminderType, Task, TaskFilters, TaskStatus, User
from workspace.services import AppServices, parse_tags


STATUS_OPTIONS = [item.value for item in TaskStatus]
PRIORITY_OPTIONS = [item.value for item in Priority]


def _clear_task_form(prefix: str) -> None:
    for key in [key for key in st.session_state if key.startswith(prefix)]:
        del st.session_state[key]


def _task_form(services: AppServices, user: User, existing: Task | None) -> None:
    users = services.users.list_active()
    user_names = {item.id: item.display_name for item in users}
    generation = st.session_state.get("task_form_generation", 0)
    prefix = f"task_form_edit_{existing.id}" if existing else f"task_form_new_{generation}"
    title = "タスク編集" if existing else "クイック追加"
    with st.expander(title, expanded=True):
        task_title = st.text_input("タイトル *", value=existing.title if existing else "", key=f"{prefix}_title")
        assignee_options = [None] + [item.id for item in users]
        current_assignee = existing.assignee_user_id if existing else user.id
        assignee_index = assignee_options.index(current_assignee) if current_assignee in assignee_options else 0
        assignee = st.selectbox(
            "担当",
            assignee_options,
            index=assignee_index,
            format_func=lambda value: "未割当" if value is None else user_names.get(value, "Unknown"),
            key=f"{prefix}_assignee",
        )
        due_enabled = st.checkbox(
            "期限を設定", value=bool(existing and existing.due_date), key=f"{prefix}_due_enabled"
        )
        due_columns = st.columns(2)
        due_date = due_columns[0].date_input(
            "期限日",
            value=existing.due_date if existing and existing.due_date else services.clock.now().date(),
            disabled=not due_enabled,
            key=f"{prefix}_due_date",
        )
        due_time_enabled = due_columns[1].checkbox(
            "期限時刻を設定",
            value=bool(existing and existing.due_time),
            disabled=not due_enabled,
            key=f"{prefix}_due_time_enabled",
        )
        due_time = due_columns[1].time_input(
            "期限時刻",
            value=existing.due_time if existing and existing.due_time else time(17),
            disabled=not due_enabled or not due_time_enabled,
            key=f"{prefix}_due_time",
        )

        with st.expander("詳細設定", expanded=True):
            description = st.text_area("説明", value=existing.description if existing else "", key=f"{prefix}_description")
            detail_columns = st.columns(2)
            status = detail_columns[0].selectbox(
                "ステータス", STATUS_OPTIONS,
                index=STATUS_OPTIONS.index(str(existing.status)) if existing else 1,
                key=f"{prefix}_status",
            )
            priority = detail_columns[1].selectbox(
                "優先度", PRIORITY_OPTIONS,
                index=PRIORITY_OPTIONS.index(str(existing.priority)) if existing else 1,
                key=f"{prefix}_priority",
            )
            start_enabled = st.checkbox(
                "開始日を設定", value=bool(existing and existing.start_date), key=f"{prefix}_start_enabled"
            )
            start_date = st.date_input(
                "開始日",
                value=existing.start_date if existing and existing.start_date else services.clock.now().date(),
                disabled=not start_enabled,
                key=f"{prefix}_start_date",
            )
            tags = st.text_input(
                "タグ（カンマ区切り）", value=", ".join(existing.tags) if existing else "", key=f"{prefix}_tags"
            )

            st.markdown("##### リマインダー")
            reminder_enabled = st.checkbox(
                "リマインダーを有効にする",
                value=bool(existing and existing.reminder_enabled),
                key=f"{prefix}_reminder_enabled",
            )
            reminder_type = st.radio(
                "通知方式",
                [ReminderType.RELATIVE.value, ReminderType.ABSOLUTE.value],
                horizontal=True,
                disabled=not reminder_enabled,
                index=1 if existing and existing.reminder_type == ReminderType.ABSOLUTE else 0,
                key=f"{prefix}_reminder_type",
            )
            offset_choices = {"10分前": 10, "30分前": 30, "1時間前": 60, "2時間前": 120, "1日前": 1440}
            current_offset = existing.reminder_offset_minutes if existing else 60
            offset_label = next((label for label, value in offset_choices.items() if value == current_offset), "1時間前")
            offset = offset_choices[st.selectbox(
                "通知タイミング",
                list(offset_choices),
                index=list(offset_choices).index(offset_label),
                disabled=not reminder_enabled or reminder_type != ReminderType.RELATIVE,
                key=f"{prefix}_reminder_offset",
            )]
            local_existing = existing.reminder_datetime if existing and existing.reminder_datetime else services.clock.now()
            reminder_columns = st.columns(2)
            reminder_date = reminder_columns[0].date_input(
                "通知日",
                value=local_existing.date(),
                disabled=not reminder_enabled or reminder_type != ReminderType.ABSOLUTE,
                key=f"{prefix}_reminder_date",
            )
            reminder_time = reminder_columns[1].time_input(
                "通知時刻",
                value=local_existing.time().replace(second=0, microsecond=0),
                disabled=not reminder_enabled or reminder_type != ReminderType.ABSOLUTE,
                key=f"{prefix}_reminder_time",
            )

            st.markdown("##### 繰り返し")
            recurrence_enabled = st.checkbox(
                "繰り返しを有効にする",
                value=bool(existing and existing.recurrence_enabled),
                key=f"{prefix}_recurrence_enabled",
            )
            recurrence_types = [item.value for item in RecurrenceType]
            recurrence_type = st.selectbox(
                "繰り返し種別",
                recurrence_types,
                index=recurrence_types.index(str(existing.recurrence_type)) if existing and existing.recurrence_type else 0,
                disabled=not recurrence_enabled,
                key=f"{prefix}_recurrence_type",
            )
            interval_label = "間隔（週）" if recurrence_type == RecurrenceType.INTERVAL else "間隔"
            interval = st.number_input(
                interval_label,
                min_value=1,
                max_value=365,
                value=existing.recurrence_interval if existing else 1,
                disabled=not recurrence_enabled,
                key=f"{prefix}_recurrence_interval",
            )
            weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
            selected_weekdays = st.multiselect(
                "曜日",
                weekday_names,
                default=[weekday_names[index] for index in existing.recurrence_weekdays]
                if existing else [weekday_names[services.clock.now().weekday()]],
                disabled=not recurrence_enabled or recurrence_type != RecurrenceType.WEEKLY,
                key=f"{prefix}_recurrence_weekdays",
            )
            month_day = st.number_input(
                "毎月の日",
                1,
                31,
                value=existing.recurrence_day_of_month if existing and existing.recurrence_day_of_month else services.clock.now().day,
                disabled=not recurrence_enabled or recurrence_type != RecurrenceType.MONTHLY,
                key=f"{prefix}_recurrence_month_day",
            )
            recurrence_time = st.time_input(
                "実行時刻",
                value=existing.recurrence_time if existing and existing.recurrence_time else time(9),
                disabled=not recurrence_enabled,
                key=f"{prefix}_recurrence_time",
            )

        action_columns = st.columns(2)
        submitted = action_columns[0].button(
            "保存", type="primary", use_container_width=True, key=f"{prefix}_save"
        )
        cancel_label = "編集をキャンセル" if existing else "閉じる"
        if action_columns[1].button(cancel_label, use_container_width=True, key=f"{prefix}_cancel"):
            _clear_task_form(prefix)
            st.session_state.pop("edit_task_id", None)
            st.session_state["show_task_form"] = False
            st.rerun()
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
                _clear_task_form(prefix)
                st.session_state["task_form_generation"] = generation + 1
                st.session_state.pop("edit_task_id", None)
                st.session_state["show_task_form"] = False
                st.rerun()


VIEW_LABELS = {
    "mine": "自分のタスク",
    "team": "チーム",
    "today": "今日",
    "upcoming": "今後",
    "recurring": "繰り返し",
    "completed": "完了履歴",
}


def _open_editor(task: Task) -> None:
    _clear_task_form(f"task_form_edit_{task.id}")
    st.session_state["edit_task_id"] = task.id
    st.session_state["show_task_form"] = True
    st.rerun()


def _render_task_actions(services: AppServices, user: User, task: Task) -> None:
    actions = st.columns([4.5, .75, .75, .42])
    if actions[1].button("編集", key=f"edit_task_{task.id}", use_container_width=True, icon=":material/edit:"):
        _open_editor(task)
    if actions[2].button(
        "完了",
        key=f"complete_task_{task.id}",
        use_container_width=True,
        icon=":material/check:",
        disabled=task.status == TaskStatus.DONE,
    ):
        if run_action(lambda: services.tasks.complete(task.id or 0, user.id or 0), "タスクを完了しました。"):
            st.rerun()
    with actions[3].popover("•••", use_container_width=True):
        st.caption(f"タスク #{task.id}")
        if st.button(
            "通知を確認済みにする",
            key=f"ack_task_{task.id}",
            use_container_width=True,
            disabled=not services.reminders.is_due(task),
        ):
            if run_action(
                lambda: services.tasks.acknowledge_reminder(task.id or 0, user.id or 0),
                "リマインダーを確認済みにしました。",
            ):
                st.rerun()
        confirm = st.checkbox("削除を確認", key=f"confirm_task_{task.id}")
        if st.button(
            "タスクを削除",
            key=f"delete_task_{task.id}",
            use_container_width=True,
            disabled=not confirm,
            type="primary",
        ):
            if run_action(lambda: services.tasks.delete(task.id or 0, user.id or 0), "タスクを削除しました。"):
                st.rerun()


def _render_task_list(
    services: AppServices,
    user: User,
    tasks: list[Task],
    user_names: dict[int, str],
) -> None:
    today = services.clock.now().date()
    if not tasks:
        st.markdown(
            '<div class="tw-empty"><strong>条件に合うタスクはありません</strong><br>'
            '<span style="font-size:.75rem">フィルターを変更するか、新しいタスクを追加してください。</span></div>',
            unsafe_allow_html=True,
        )
        return
    render_list_heading(len(tasks))
    for task in tasks:
        card_key = f"task_card_{priority_slug(task)}_{task.id}"
        with st.container(border=True, key=card_key):
            st.markdown(
                task_card_markup(
                    task,
                    user_names.get(task.assignee_user_id or -1, "未割当"),
                    today,
                ),
                unsafe_allow_html=True,
            )
            _render_task_actions(services, user, task)


def _sort_tasks(tasks: list[Task], order: str) -> list[Task]:
    if order == "priority":
        rank = {Priority.CRITICAL: 0, Priority.HIGH: 1, Priority.MEDIUM: 2, Priority.LOW: 3}
        return sorted(tasks, key=lambda task: (rank[Priority(task.priority)], task.due_date is None, task.due_date))
    if order == "updated":
        return sorted(tasks, key=lambda task: task.updated_at or task.created_at or datetime.min.replace(tzinfo=ZoneInfo("UTC")), reverse=True)
    return sorted(tasks, key=lambda task: (task.due_date is None, task.due_date, task.due_time is None, task.due_time))


def _render_history(services: AppServices) -> None:
    history = services.tasks_repo.completion_history()
    if not history:
        st.markdown('<div class="tw-empty">完了履歴はまだありません。</div>', unsafe_allow_html=True)
        return
    for item in history:
        scheduled = f" · 対象日 {escape(str(item['scheduled_for']))}" if item.get("scheduled_for") else ""
        st.markdown(
            f'<div class="tw-history-row"><strong>{escape(str(item["title"]))}</strong>'
            f'<div>{escape(str(item["display_name"]))} · '
            f'{escape(format_timestamp(str(item["completed_at"])))}{scheduled}</div></div>',
            unsafe_allow_html=True,
        )


def render(services: AppServices, user: User) -> None:
    inject_task_styles()
    header, create_action = st.columns([5, 1.15], vertical_alignment="bottom")
    with header:
        render_task_header()
    if create_action.button(
        "新しいタスク",
        type="primary",
        use_container_width=True,
        icon=":material/add:",
    ):
        st.session_state.pop("edit_task_id", None)
        st.session_state["show_task_form"] = True
        st.rerun()

    edit_id = st.session_state.get("edit_task_id")
    existing = services.tasks.get(edit_id) if edit_id else None
    if existing or st.session_state.get("show_task_form", False):
        _task_form(services, user, existing)

    users = services.users.list_all()
    user_names = {item.id or 0: item.display_name for item in users}
    all_my_tasks = services.tasks.list(TaskFilters(assignee_user_id=user.id))
    render_task_stats(all_my_tasks, services.clock.now().date())

    st.markdown("#### タスク一覧")
    view = st.segmented_control(
        "表示範囲",
        list(VIEW_LABELS),
        default="mine",
        format_func=VIEW_LABELS.get,
        selection_mode="single",
        label_visibility="collapsed",
        key="task_view",
    ) or "mine"

    if view == "completed":
        _render_history(services)
        return

    filter_columns = st.columns([2.2, 1.6, 1.4, 1.2], vertical_alignment="bottom")
    text = filter_columns[0].text_input(
        "キーワード",
        placeholder="タイトル・説明・タグを検索",
        key="task_filter_text",
        icon=":material/search:",
    )
    statuses = filter_columns[1].multiselect(
        "ステータス",
        STATUS_OPTIONS,
        default=[],
        format_func=lambda value: STATUS_LABELS[TaskStatus(value)],
        placeholder="すべて",
        key="task_filter_status",
    )
    priorities = filter_columns[2].multiselect(
        "優先度",
        PRIORITY_OPTIONS,
        default=[],
        format_func=lambda value: PRIORITY_LABELS[Priority(value)],
        placeholder="すべて",
        key="task_filter_priority",
    )
    order = filter_columns[3].selectbox(
        "並び順",
        ["due", "priority", "updated"],
        format_func={"due": "期限が近い", "priority": "優先度", "updated": "更新が新しい"}.get,
        key="task_sort_order",
    )

    filters = TaskFilters(statuses=statuses, priorities=priorities, text=text or None)
    if view == "mine":
        filters.assignee_user_id = user.id
    if view == "today":
        filters.due_from = filters.due_to = services.clock.now().date()
    if view == "upcoming":
        filters.due_from = services.clock.now().date()
    if view == "recurring":
        filters.recurring_only = True
    filtered_tasks = _sort_tasks(services.tasks.list(filters), order)
    _render_task_list(services, user, filtered_tasks, user_names)
