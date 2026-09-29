from __future__ import annotations

from typing import Any

import streamlit as st

from views.common import run_action
from workspace.models import User
from workspace.services import AppServices, parse_tags


CONFIG = {
    "snippet": {
        "label": "Snippets", "title_field": "title",
        "fields": [("title", "タイトル", "text"), ("description", "説明", "area"), ("content", "内容", "code"),
                   ("language", "言語", "text"), ("category", "カテゴリ", "text")],
    },
    "link": {
        "label": "Links", "title_field": "title",
        "fields": [("title", "タイトル", "text"), ("url", "URL", "text"),
                   ("description", "説明", "area"), ("category", "カテゴリ", "text")],
    },
    "glossary": {
        "label": "Glossary", "title_field": "term",
        "fields": [("term", "用語", "text"), ("abbreviation", "略称", "text"),
                   ("definition", "定義", "area"), ("category", "カテゴリ", "text"),
                   ("related_terms", "関連用語", "text"), ("related_links", "関連リンク", "area")],
    },
    "note": {
        "label": "Notes / Knowledge", "title_field": "title",
        "fields": [("title", "タイトル", "text"), ("content", "Markdown本文", "area"),
                   ("category", "カテゴリ", "text")],
    },
}


def _input(field: str, label: str, kind: str, value: Any) -> str:
    if kind in ("area", "code"):
        return st.text_area(label, value=str(value or ""), height=180 if kind == "code" else 120)
    return st.text_input(label, value=str(value or ""))


def render(services: AppServices, user: User, entity_type: str) -> None:
    config = CONFIG[entity_type]
    repository = services.content_repositories[entity_type]
    service = services.content[entity_type]
    st.title(config["label"])
    edit_key = f"edit_{entity_type}_id"
    edit_id = st.session_state.get(edit_key)
    existing = repository.find_by_id(edit_id) if edit_id else None
    with st.expander("編集" if existing else "新規追加", expanded=existing is not None):
        with st.form(f"{entity_type}_form_{edit_id or 'new'}"):
            values: dict[str, Any] = {}
            for field, label, kind in config["fields"]:
                values[field] = _input(field, label, kind, existing.get(field, "") if existing else "")
            values["tags"] = parse_tags(st.text_input("タグ（カンマ区切り）", value=", ".join(existing.get("tags", [])) if existing else ""))
            if st.form_submit_button("保存", type="primary", use_container_width=True):
                if run_action(lambda: service.save(values, user.id or 0, edit_id), "保存しました。"):
                    st.session_state.pop(edit_key, None); st.rerun()

    search_col, category_col, tag_col = st.columns(3)
    search = search_col.text_input("検索", key=f"search_{entity_type}")
    categories = [""] + repository.categories()
    category = category_col.selectbox("カテゴリ", categories, format_func=lambda value: value or "すべて", key=f"category_{entity_type}")
    tag = tag_col.text_input("タグ", key=f"tag_{entity_type}")
    items = repository.find_all(search, category, tag)
    st.caption(f"{len(items)} 件")
    for item in items:
        title = str(item[config["title_field"]])
        favorite = services.favorites.is_favorite(user.id or 0, entity_type, item["id"])
        with st.expander(("★ " if favorite else "") + title):
            if entity_type == "snippet":
                if item.get("description"): st.write(item["description"])
                st.code(item["content"], language=item.get("language") or None)
                st.caption(f"Category: {item['category']} · Usage: {item['usage_count']} · Tags: {', '.join(item['tags'])}")
            elif entity_type == "link":
                st.link_button("リンクを開く", item["url"])
                st.write(item.get("description", ""))
                st.caption(f"{item['category']} · {', '.join(item['tags'])}")
            elif entity_type == "glossary":
                if item.get("abbreviation"): st.caption(f"略称: {item['abbreviation']}")
                st.write(item["definition"])
                if item.get("related_terms"): st.write(f"関連用語: {item['related_terms']}")
                if item.get("related_links"): st.write(f"関連リンク: {item['related_links']}")
            else:
                st.markdown(item["content"])
                st.caption(f"{item['category']} · {', '.join(item['tags'])}")
            cols = st.columns(4)
            if cols[0].button("Favorite解除" if favorite else "Favorite", key=f"fav_{entity_type}_{item['id']}"):
                services.favorites.toggle(user.id or 0, entity_type, item["id"]); st.rerun()
            if cols[1].button("編集", key=f"edit_{entity_type}_{item['id']}"):
                st.session_state[edit_key] = item["id"]; st.rerun()
            confirm = cols[2].checkbox("削除確認", key=f"confirm_{entity_type}_{item['id']}")
            if cols[3].button("削除", key=f"delete_{entity_type}_{item['id']}", disabled=not confirm):
                if run_action(lambda entity_id=item["id"]: service.delete(entity_id, user.id or 0), "削除しました。"):
                    st.rerun()

