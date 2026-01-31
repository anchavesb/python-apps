import json
import os
import tempfile
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


def test_todo_crud(client):
    # Create
    resp = client.post("/api/todos", json={
        "title": "Test Todo",
        "description": "desc",
        "tags": {"category": "work", "priority": "high"},
        "due_date": "2030-01-01",
    })
    assert resp.status_code == 201
    todo = resp.get_json()
    tid = todo["id"]

    # Read
    resp = client.get(f"/api/todos/{tid}")
    assert resp.status_code == 200

    # Update
    resp = client.patch(f"/api/todos/{tid}", json={"done": True})
    assert resp.status_code == 200
    assert resp.get_json()["done"] is True

    # Delete
    resp = client.delete(f"/api/todos/{tid}")
    assert resp.status_code == 204


def test_note_crud(client):
    # Create
    resp = client.post("/api/notes", json={
        "title": "Test Note",
        "note": "hello",
        "tags": {"category": "personal", "priority": "low"},
    })
    assert resp.status_code == 201
    note = resp.get_json()
    nid = note["id"]

    # Update
    resp = client.patch(f"/api/notes/{nid}", json={"note": "world"})
    assert resp.status_code == 200
    assert resp.get_json()["note"] == "world"

    # Delete
    resp = client.delete(f"/api/notes/{nid}")
    assert resp.status_code == 204


def test_validation(client):
    # Missing required tags
    resp = client.post("/api/todos", json={"title": "X", "tags": {"category": "c"}})
    assert resp.status_code == 400

    # Invalid priority
    resp = client.post("/api/notes", json={"title": "Y", "tags": {"category": "c", "priority": "p"}})
    assert resp.status_code == 400


def test_backups_and_wal_recovery(tmp_path):
    data_file = tmp_path / "appdata.json"
    wal_file = tmp_path / "appdata.wal"
    app = create_app({"DATA_FILE": str(data_file), "WAL_FILE": str(wal_file), "DEBUG": False, "TESTING": True})

    with app.app_context():
        s = app.extensions["store"]
        todo = s.create_todo({
            "title": "Persist",
            "tags": {"category": "work", "priority": "medium"}
        })
        tid = todo["id"]
        # Corrupt the data file
        with open(data_file, "w", encoding="utf-8") as f:
            f.write("{ broken json")

    # Recreate app to trigger recovery
    app2 = create_app({"DATA_FILE": str(data_file), "WAL_FILE": str(wal_file), "DEBUG": False, "TESTING": True})
    with app2.app_context():
        s2 = app2.extensions["store"]
        # Should recover from WAL or backup
        todos = s2.list_todos()
        assert any(t["id"] == tid for t in todos)
