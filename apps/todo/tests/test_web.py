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
    r.get_json()["id"]

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
    assert "<script>alert" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_note_redirects_to_notes_tab(client):
    # 1. Test creation redirect
    r = client.post("/notes/new", data={"title": "Web Note", "note": "Content", "tags_text": "category=web"})
    assert r.status_code == 302
    assert r.location.endswith("/?tab=notes")

    # Get the note id from storage via API
    r_api = client.get("/api/notes")
    assert r_api.status_code == 200
    notes = r_api.get_json()
    assert len(notes) > 0
    nid = notes[0]["id"]

    # 2. Test edit redirect (GET invalid note)
    r = client.get("/notes/invalid_id/edit")
    assert r.status_code == 302
    assert r.location.endswith("/?tab=notes")

    # 3. Test edit redirect (POST valid note edit)
    r_detail = client.get(f"/api/notes/{nid}")
    assert r_detail.status_code == 200
    updated_at = r_detail.get_json()["updated_at"]

    r = client.post(f"/notes/{nid}/edit", data={"title": "Edited Title", "note": "New Content", "last_updated_at": updated_at})
    assert r.status_code == 302
    assert "/?tab=notes" in r.location
    assert f"updated_note_id={nid}" in r.location

    # 4. Test delete redirect
    r = client.post(f"/notes/{nid}/delete")
    assert r.status_code == 302
    assert "/?tab=notes" in r.location
    assert f"deleted_note_id={nid}" in r.location


def test_note_optimistic_locking(client):
    # 1. Create a note via API
    r = client.post("/api/notes", json={"title": "Locking Note", "note": "v1"})
    assert r.status_code == 201
    note = r.get_json()
    nid = note["id"]
    original_updated_at = note["updated_at"]

    # 2. Get edit page to ensure it contains last_updated_at field
    r_edit_page = client.get(f"/notes/{nid}/edit")
    assert r_edit_page.status_code == 200
    html = r_edit_page.get_data(as_text=True)
    assert 'name="last_updated_at"' in html
    assert original_updated_at in html

    # 3. Simulate another tab updating the note
    import time
    time.sleep(1.1)
    r_api_update = client.put(f"/api/notes/{nid}", json={"title": "Locking Note", "note": "v2"})
    assert r_api_update.status_code == 200
    new_updated_at = r_api_update.get_json()["updated_at"]
    assert original_updated_at != new_updated_at

    # 4. Try to save from the current tab with the stale original_updated_at
    r_save_stale = client.post(
        f"/notes/{nid}/edit",
        data={
            "title": "Stale Edit",
            "note": "v3",
            "last_updated_at": original_updated_at
        }
    )
    assert r_save_stale.status_code == 200  # returns the re-rendered form
    stale_html = r_save_stale.get_data(as_text=True)
    assert "Conflict detected!" in stale_html
    assert 'name="force_save"' in stale_html

    # Verify note in DB was NOT updated to "Stale Edit" / "v3"
    r_check = client.get(f"/api/notes/{nid}")
    assert r_check.get_json()["note"] == "v2"

    # 5. Save again with force_save=true
    r_save_force = client.post(
        f"/notes/{nid}/edit",
        data={
            "title": "Forced Edit",
            "note": "v4",
            "last_updated_at": original_updated_at,
            "force_save": "true"
        }
    )
    assert r_save_force.status_code == 302
    assert f"updated_note_id={nid}" in r_save_force.location

    # Verify note in DB IS updated to "v4"
    r_check = client.get(f"/api/notes/{nid}")
    assert r_check.get_json()["note"] == "v4"

