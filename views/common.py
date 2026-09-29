from __future__ import annotations

from datetime import datetime
from typing import Any

import streamlit as st

from workspace.errors import WorkspaceError
from workspace.models import Task


ENTITY_LABELS = {"task": "タスク", "snippet": "スニペット", "link": "リンク", "glossary": "用語", "note": "ノート"}


def run_action(action, success: str) -> bool:
    try:
        action()
        st.success(success)
        return True
    except WorkspaceError as exc:
        st.error(str(exc))
    except Exception:
        st.error("処理に失敗しました。詳細は logs/workspace.log を確認してください。")
    return False


def task_label(task: Task) -> str:
    due = task.due_date.isoformat() if task.due_date else "期限なし"
    if task.due_time:
        due += f" {task.due_time.strftime('%H:%M')}"
    return f"#{task.id} {task.title} — {due} / {task.status}"


def task_rows(tasks: list[Task], users: dict[int, str]) -> list[dict[str, Any]]:
    return [{
        "ID": task.id,
        "タイトル": task.title,
        "ステータス": str(task.status),
        "優先度": str(task.priority),
        "担当": users.get(task.assignee_user_id or -1, "未割当"),
        "期限日": task.due_date.isoformat() if task.due_date else "",
        "時刻": task.due_time.strftime("%H:%M") if task.due_time else "",
        "繰り返し": str(task.recurrence_type or ""),
        "タグ": ", ".join(task.tags),
    } for task in tasks]


def format_timestamp(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value

