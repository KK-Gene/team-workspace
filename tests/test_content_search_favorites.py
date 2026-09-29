import pytest


@pytest.mark.parametrize(("kind", "values", "title"), [
    ("snippet", {"title": "Allocation SQL", "description": "", "content": "SELECT 1", "language": "sql", "category": "SQL", "tags": ["allocation"]}, "Allocation SQL"),
    ("link", {"title": "Design", "url": "https://example.com", "description": "Allocation design", "category": "Docs", "tags": []}, "Design"),
    ("glossary", {"term": "Allocation", "abbreviation": "ALLOC", "definition": "Assigning stock", "category": "Domain", "related_terms": "", "related_links": "", "tags": []}, "Allocation"),
    ("note", {"title": "Allocation memo", "content": "# Notes", "category": "Memo", "tags": []}, "Allocation memo"),
])
def test_content_crud(services, user, kind, values, title):
    item = services.content[kind].save(values, user.id)
    assert item["id"]
    title_field = "term" if kind == "glossary" else "title"
    assert item[title_field] == title
    assert services.content_repositories[kind].find_by_id(item["id"])
    services.content[kind].delete(item["id"], user.id)
    assert services.content_repositories[kind].find_by_id(item["id"]) is None


def test_global_search_and_favorite(services, user):
    item = services.content["snippet"].save({
        "title": "Allocation validation", "description": "", "content": "SELECT * FROM allocation",
        "language": "sql", "category": "SQL", "tags": ["allocation"],
    }, user.id)
    results = services.search.search("allocation")
    assert any(result["entity_type"] == "snippet" for result in results)
    assert services.favorites.toggle(user.id, "snippet", item["id"])
    assert services.favorites.is_favorite(user.id, "snippet", item["id"])
    assert services.favorites.list_for_user(user.id)[0]["title"] == "Allocation validation"
    assert not services.favorites.toggle(user.id, "snippet", item["id"])

