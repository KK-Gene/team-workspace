from __future__ import annotations

from datetime import date
from html import escape
from typing import Iterable

import streamlit as st

from workspace.models import Priority, Task, TaskStatus


STATUS_LABELS = {
    TaskStatus.BACKLOG: "バックログ",
    TaskStatus.TODO: "未着手",
    TaskStatus.IN_PROGRESS: "進行中",
    TaskStatus.BLOCKED: "ブロック",
    TaskStatus.DONE: "完了",
}

PRIORITY_LABELS = {
    Priority.LOW: "低",
    Priority.MEDIUM: "中",
    Priority.HIGH: "高",
    Priority.CRITICAL: "最優先",
}

def inject_task_styles() -> None:
    st.markdown(
        """
        <style>
        .tw-task-hero {
            position: relative;
            overflow: hidden;
            padding: 1.35rem 1.5rem;
            border: 1px solid #dbe5f2;
            border-radius: 1rem;
            background:
                radial-gradient(circle at 92% 18%, rgba(37, 99, 235, .17), transparent 34%),
                linear-gradient(135deg, #f8fbff 0%, #eef5ff 58%, #f8fafc 100%);
        }
        .tw-task-eyebrow {
            margin-bottom: .35rem;
            color: #2563eb;
            font-size: .7rem;
            font-weight: 750;
            letter-spacing: .12em;
        }
        .tw-task-hero h1 {
            margin: 0;
            color: #0f172a;
            font-size: clamp(1.65rem, 2.6vw, 2.25rem);
            line-height: 1.1;
            letter-spacing: -.035em;
        }
        .tw-task-hero p {
            max-width: 42rem;
            margin: .55rem 0 0;
            color: #64748b;
            font-size: .9rem;
        }
        .tw-stat {
            min-height: 6rem;
            padding: .85rem 1rem;
            border: 1px solid #e2e8f0;
            border-radius: .85rem;
            background: #ffffff;
            box-shadow: 0 4px 14px rgba(15, 23, 42, .035);
        }
        .tw-stat-label { color: #64748b; font-size: .72rem; font-weight: 650; }
        .tw-stat-value { margin-top: .25rem; color: #0f172a; font-size: 1.55rem; font-weight: 760; }
        .tw-stat-note { color: #94a3b8; font-size: .68rem; }
        .tw-stat-blue { border-top: 3px solid #3b82f6; }
        .tw-stat-amber { border-top: 3px solid #f59e0b; }
        .tw-stat-red { border-top: 3px solid #ef4444; }
        .tw-stat-green { border-top: 3px solid #10b981; }
        .tw-list-heading {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin: .7rem 0 .35rem;
            padding: .55rem .15rem;
            border-bottom: 1px solid #e2e8f0;
        }
        .tw-list-heading strong { color: #334155; font-size: .78rem; }
        .tw-list-heading span { color: #94a3b8; font-size: .7rem; }
        [class*="st-key-task_card_"] {
            margin-bottom: .45rem;
            border: 1px solid #e2e8f0 !important;
            border-left-width: 4px !important;
            border-radius: .7rem !important;
            background: #ffffff;
            box-shadow: 0 2px 8px rgba(15, 23, 42, .035);
            transition: transform .16s ease, box-shadow .16s ease;
        }
        [class*="st-key-task_card_"]:hover {
            transform: translateY(-1px);
            box-shadow: 0 9px 22px rgba(15, 23, 42, .08);
        }
        [class*="task_card_critical_"] { border-left-color: #dc2626 !important; }
        [class*="task_card_high_"] { border-left-color: #f97316 !important; }
        [class*="task_card_medium_"] { border-left-color: #3b82f6 !important; }
        [class*="task_card_low_"] { border-left-color: #94a3b8 !important; }
        [class*="st-key-task_card_"] [data-testid="stVerticalBlock"] { gap: .48rem; }
        [class*="st-key-task_card_"] button { min-height: 2rem; font-size: .75rem; }
        .tw-card-top { display: flex; align-items: center; gap: .35rem; flex-wrap: wrap; }
        .tw-list-card-body {
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto;
            gap: .75rem 1.25rem;
            align-items: center;
        }
        .tw-card-main { min-width: 0; }
        .tw-card-side {
            display: grid;
            min-width: 10.5rem;
            gap: .22rem;
            color: #64748b;
            font-size: .68rem;
            text-align: right;
        }
        .tw-badge {
            display: inline-flex;
            align-items: center;
            padding: .18rem .48rem;
            border-radius: 999px;
            font-size: .62rem;
            font-weight: 760;
            letter-spacing: .02em;
        }
        .tw-status-backlog, .tw-status-todo { color: #475569; background: #f1f5f9; }
        .tw-status-in-progress { color: #1d4ed8; background: #dbeafe; }
        .tw-status-blocked { color: #be123c; background: #ffe4e6; }
        .tw-status-done { color: #047857; background: #d1fae5; }
        .tw-priority-low { color: #64748b; background: #f1f5f9; }
        .tw-priority-medium { color: #1d4ed8; background: #eff6ff; }
        .tw-priority-high { color: #c2410c; background: #ffedd5; }
        .tw-priority-critical { color: #b91c1c; background: #fee2e2; }
        .tw-card-title {
            margin: .1rem 0 0;
            color: #172033;
            font-size: .92rem;
            font-weight: 720;
            line-height: 1.35;
        }
        .tw-card-description {
            display: -webkit-box;
            overflow: hidden;
            margin: 0;
            color: #64748b;
            font-size: .72rem;
            line-height: 1.45;
            -webkit-box-orient: vertical;
            -webkit-line-clamp: 2;
        }
        .tw-card-signals {
            display: flex;
            gap: .35rem .6rem;
            flex-wrap: wrap;
            margin-top: .35rem;
            color: #64748b;
            font-size: .68rem;
        }
        .tw-due-overdue { color: #dc2626; font-weight: 700; }
        .tw-due-today { color: #d97706; font-weight: 700; }
        .tw-tags { display: flex; gap: .28rem; flex-wrap: wrap; }
        .tw-tag {
            padding: .14rem .4rem;
            border-radius: .35rem;
            color: #475569;
            background: #f1f5f9;
            font-size: .61rem;
        }
        .tw-empty {
            padding: 2.4rem 1rem;
            border: 1px dashed #cbd5e1;
            border-radius: .9rem;
            color: #64748b;
            background: #f8fafc;
            text-align: center;
        }
        .tw-history-row {
            margin-bottom: .55rem;
            padding: .8rem 1rem;
            border: 1px solid #e2e8f0;
            border-left: 4px solid #10b981;
            border-radius: .75rem;
            background: white;
        }
        .tw-history-row strong { color: #172033; font-size: .86rem; }
        .tw-history-row div { margin-top: .25rem; color: #64748b; font-size: .7rem; }
        @media (max-width: 900px) {
            .tw-task-hero { padding: 1.1rem; }
            [class*="st-key-task_card_"] { margin-bottom: .5rem; }
            .tw-list-card-body { grid-template-columns: 1fr; }
            .tw-card-side { min-width: 0; text-align: left; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_task_header() -> None:
    st.markdown(
        """
        <section class="tw-task-hero">
          <div class="tw-task-eyebrow">WORK MANAGEMENT</div>
          <h1>Tasks</h1>
          <p>優先順位、進捗、期限をひとつのボードで把握。次に動かす仕事がすぐ見つかります。</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_task_stats(tasks: Iterable[Task], today: date) -> None:
    items = list(tasks)
    in_progress = sum(task.status == TaskStatus.IN_PROGRESS for task in items)
    overdue = sum(bool(task.due_date and task.due_date < today and task.status != TaskStatus.DONE) for task in items)
    due_today = sum(bool(task.due_date == today and task.status != TaskStatus.DONE) for task in items)
    completed = sum(task.status == TaskStatus.DONE for task in items)
    stats = (
        ("blue", "進行中", in_progress, "現在対応しているタスク"),
        ("amber", "今日が期限", due_today, "本日中の対応が必要"),
        ("red", "期限超過", overdue, "優先して確認"),
        ("green", "完了", completed, "完了済みタスク"),
    )
    columns = st.columns(4)
    for column, (tone, label, value, note) in zip(columns, stats, strict=True):
        column.markdown(
            f'<div class="tw-stat tw-stat-{tone}"><div class="tw-stat-label">{label}</div>'
            f'<div class="tw-stat-value">{value}</div><div class="tw-stat-note">{note}</div></div>',
            unsafe_allow_html=True,
        )


def render_list_heading(count: int) -> None:
    st.markdown(
        f'<div class="tw-list-heading"><strong>タスク</strong><span>{count}件を表示</span></div>',
        unsafe_allow_html=True,
    )


def task_card_markup(task: Task, assignee: str, today: date) -> str:
    status = TaskStatus(task.status)
    priority = Priority(task.priority)
    status_slug = status.value.lower().replace(" ", "-")
    priority_slug = priority.value.lower()
    due_text, due_class = _due_text(task, today)
    description = (
        f'<p class="tw-card-description">{escape(task.description)}</p>' if task.description else ""
    )
    tags = "".join(f'<span class="tw-tag">{escape(tag)}</span>' for tag in task.tags[:4])
    tag_block = f'<div class="tw-tags">{tags}</div>' if tags else ""
    recurrence = "<span>↻ 繰り返し</span>" if task.recurrence_enabled else ""
    reminder = "<span>◷ 通知あり</span>" if task.reminder_enabled else ""
    return (
        '<div class="tw-list-card-body"><div class="tw-card-main">'
        '<div class="tw-card-top">'
        f'<span class="tw-badge tw-status-{status_slug}">{STATUS_LABELS[status]}</span>'
        f'<span class="tw-badge tw-priority-{priority_slug}">{PRIORITY_LABELS[priority]}</span>'
        '</div>'
        f'<div class="tw-card-title">{escape(task.title)}</div>{description}'
        f'<div class="tw-card-signals">{tag_block}{recurrence}{reminder}</div></div>'
        '<div class="tw-card-side">'
        f'<span class="{due_class}">期限 {escape(due_text)}</span>'
        f'<span>担当 {escape(assignee)}</span>'
        f'<span>#{task.id}</span></div></div>'
    )


def priority_slug(task: Task) -> str:
    return Priority(task.priority).value.lower()


def _due_text(task: Task, today: date) -> tuple[str, str]:
    if not task.due_date:
        return "未設定", ""
    time_suffix = f" {task.due_time.strftime('%H:%M')}" if task.due_time else ""
    days = (task.due_date - today).days
    if task.status != TaskStatus.DONE and days < 0:
        return f"{abs(days)}日超過{time_suffix}", "tw-due-overdue"
    if task.status != TaskStatus.DONE and days == 0:
        return f"今日{time_suffix}", "tw-due-today"
    if days == 1:
        return f"明日{time_suffix}", ""
    return f"{task.due_date.strftime('%m/%d')}{time_suffix}", ""
