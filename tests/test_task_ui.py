from datetime import date

from streamlit.testing.v1 import AppTest

from workspace.models import Priority, Task, TaskStatus


def _task(services, user, title: str, status: TaskStatus, priority: Priority) -> Task:
    return services.tasks.save(
        Task(
            title=title,
            description=f"{title} description",
            created_by=user.id or 0,
            assignee_user_id=user.id,
            due_date=date(2026, 10, 2),
            status=status,
            priority=priority,
        ),
        user.id or 0,
    )


def _render_app(services, user, *, show_form: bool = False) -> AppTest:
    database_path = services.database.path.as_posix()
    script = f"""
from datetime import datetime
from pathlib import Path
from views.tasks import render
from workspace.clock import FixedClock
from workspace.database import Database
from workspace.services import AppServices
import streamlit as st

database = Database(Path({database_path!r}))
clock = FixedClock(datetime.fromisoformat('2026-10-02T12:00:00+09:00'))
services = AppServices(database, clock, Path({database_path!r}).parent / 'backups', 'Asia/Tokyo', 3)
user = services.users.find_by_username({user.username!r})
st.session_state['show_task_form'] = {show_form!r}
render(services, user)
"""
    return AppTest.from_string(script, default_timeout=5).run()


def test_task_list_renders_status_cards_and_filters(services, user):
    _task(services, user, "Ready work", TaskStatus.TODO, Priority.MEDIUM)
    _task(services, user, "Active work", TaskStatus.IN_PROGRESS, Priority.HIGH)
    _task(services, user, "Waiting work", TaskStatus.BLOCKED, Priority.CRITICAL)
    _task(services, user, "Finished work", TaskStatus.DONE, Priority.LOW)

    app = _render_app(services, user)

    assert not app.exception
    markup = "\n".join(element.value for element in app.markdown)
    assert "tw-task-hero" in markup
    assert "Ready work" in markup
    assert "Active work" in markup
    assert "Waiting work" in markup
    assert "Finished work" in markup
    assert "4件を表示" in markup
    assert not app.dataframe
    assert len([button for button in app.button if button.label == "編集"]) == 4
    assert len([button for button in app.button if button.label == "完了"]) == 4


def test_new_task_button_opens_reactive_form(services, user):
    app = _render_app(services, user, show_form=True)

    assert not app.exception
    assert any(field.label == "タイトル *" for field in app.text_input)
    assert any(checkbox.label == "期限を設定" for checkbox in app.checkbox)
    assert any(checkbox.label == "リマインダーを有効にする" for checkbox in app.checkbox)
    assert any(checkbox.label == "繰り返しを有効にする" for checkbox in app.checkbox)
