import streamlit as st

from workspace.models import User
from workspace.services import AppServices


def render(services: AppServices, user: User) -> None:
    st.title("Favorites")
    items = services.favorites.list_for_user(user.id or 0)
    if not items:
        st.info("まだ Favorite はありません。Snippets、Links、Glossary、Notes から登録できます。")
        return
    for item in items:
        st.write(f"★ **{item['title']}**")
        st.caption(item["entity_type"])

