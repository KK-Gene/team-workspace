import pandas as pd
import streamlit as st

from views.common import format_timestamp
from workspace.models import User
from workspace.services import AppServices


def render(services: AppServices, user: User) -> None:
    st.title("Activity")
    items = services.activity.list_recent(500)
    entity_types = sorted({item["entity_type"] for item in items})
    selected = st.multiselect("対象", entity_types)
    if selected:
        items = [item for item in items if item["entity_type"] in selected]
    rows = [{
        "日時": format_timestamp(item["created_at"]), "ユーザー": item["user_name"], "操作": item["action"],
        "種類": item["entity_type"], "対象": item["entity_title"], "詳細": item["details"],
    } for item in items]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

