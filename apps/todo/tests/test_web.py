import pytest
from todo_app import create_app

@pytest.fixture()
def client(tmp_path):
    data_file = tmp_path / "appdata.json"
    wal_file = tmp_path / "appdata.wal"
    app = create_app({
        "DATA_FILE": str(data_file),
        "WAL_FILE": str(wal_file),
        "DEBUG": False,
        "TESTING": True,
    })
    with app.test_client() as c:
        yield c


def _positions(html: str, titles: list[str]) -> list[int]:
    return [html.find(t) for t in titles]


def test_index_sort_todos_by_due_date(client):
    # Create todos with different due dates
    todos = [
        {"title": "C - no due", "tags": {"category": "work", "priority": "low"}},
        {"title": "A - due 2030-01-01", "due_date": "2030-01-01", "tags": {"category": "work", "priority": "low"}},
        {"title": "B - due 2030-01-05", "due_date": "2030-01-05", "tags": {"category": "work", "priority": "low"}},
    ]
    for t in todos:
        r = client.post("/api/todos", json=t)
        assert r.status_code == 201

    r = client.get("/?sort=due_date&order=asc")
    assert r.status_code == 200
    html = r.get_data(as_text=True)

    # Expect order: A (earliest), B, C (no due last)
    titles = ["A - due 2030-01-01", "B - due 2030-01-05", "C - no due"]
    pos = _positions(html, titles)
    assert all(p >= 0 for p in pos)
    assert pos == sorted(pos)


def test_index_sort_todos_by_status(client):
    # Create open and done todos
    r = client.post("/api/todos", json={"title": "Open", "tags": {"category": "c", "priority": "medium"}})
    assert r.status_code == 201
    open_id = r.get_json()["id"]

    r = client.post("/api/todos", json={"title": "Done", "tags": {"category": "c", "priority": "medium"}})
    assert r.status_code == 201
    done_id = r.get_json()["id"]

    # Mark one as done
    r = client.post(f"/api/todos/{done_id}/done")
    assert r.status_code == 200

    r = client.get("/?sort=status&order=asc")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    pos_open = html.find("Open")
    pos_done = html.find("Done")
    assert pos_open >= 0 and pos_done >= 0
    # open first for asc
    assert pos_open < pos_done


def test_index_sort_notes_by_priority(client):
    # Create notes with different priorities
    r = client.post("/api/notes", json={"title": "Low Note", "note": "text", "tags": {"category": "c", "priority": "low"}})
    assert r.status_code == 201
    r = client.post("/api/notes", json={"title": "Urgent Note", "note": "text", "tags": {"category": "c", "priority": "urgent"}})
    assert r.status_code == 201

    r = client.get("/?sort=priority&order=asc")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    pos_urgent = html.find("Urgent Note")
    pos_low = html.find("Low Note")
    assert pos_urgent >= 0 and pos_low >= 0
    assert pos_urgent < pos_low  # urgent should come before low


def test_markdown_rendering_safe(client):
    note_md = "Hello **bold** `code` https://example.com <script>alert(1)</script>"
    r = client.post(
        "/api/notes",
        json={
            "title": "MD Note",
            "note": note_md,
            "tags": {"category": "c", "priority": "medium"},
        },
    )
    assert r.status_code == 201

    r = client.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)

    # Should render bold and code (either via markdown/bleach or fallback)
    assert "<strong>bold</strong>" in html or "<b>bold</b>" in html
    assert "<code>code</code>" in html
    # Should linkify the URL in either path
    assert "example.com" in html
    # Script tags must not be present; escaped version should be present
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
