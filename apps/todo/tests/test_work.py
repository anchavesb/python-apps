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


def test_work_crud_via_web(client):
    # Create
    resp = client.post(
        "/work/new",
        data={
            "name": "Quarterly Review",
            "start_date": "2030-01-01",
            "end_date": "2030-01-31",
            "description": "Prepared and delivered Q1 review",
            "why": "align stakeholders and drive priorities",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)

    # Fetch from store to get ID
    store = client.application.extensions["store"]
    items = store.list_work()
    wid = next(w["id"] for w in items if w["name"] == "Quarterly Review")

    # Edit
    resp = client.post(
        f"/work/{wid}/edit",
        data={
            "name": "Quarterly Review",
            "start_date": "2030-01-01",
            "end_date": "2030-01-31",
            "description": "Updated desc",
            "why": "Updated why",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    updated = store.get_work(wid)
    assert updated["description"] == "Updated desc"
    assert updated["why"] == "Updated why"

    # Delete
    resp = client.post(f"/work/{wid}/delete")
    assert resp.status_code in (302, 303)
    assert store.get_work(wid) is None


def test_work_filter_by_date_and_search(client):
    store = client.application.extensions["store"]
    # Seed data
    store.create_work({
        "name": "Alpha",
        "start_date": "2030-01-01",
        "end_date": "2030-01-10",
        "description": "Initial planning",
        "why": "foundation",
    })
    store.create_work({
        "name": "Beta",
        "start_date": "2030-02-01",
        "end_date": "2030-02-20",
        "description": "Execution phase",
        "why": "adds business value",
    })
    store.create_work({
        "name": "Gamma",
        "start_date": "2030-03-01",
        "end_date": None,
        "description": "Wrap-up",
        "why": "documentation",
    })

    # Filter by Feb window: expect Beta only
    r = client.get("/?tab=work&ws_from=2030-02-01&ws_to=2030-02-28")
    html = r.get_data(as_text=True)
    assert "Beta" in html
    assert "Alpha" not in html
    assert "Gamma" not in html

    # Search on 'value' (why)
    r = client.get("/?tab=work&wq=value")
    html = r.get_data(as_text=True)
    assert "Beta" in html  # has 'adds business value'
    # Others may also appear depending on filters; we assert Beta is present


def test_work_sorting(client):
    store = client.application.extensions["store"]
    store.create_work({
        "name": "C Item",
        "start_date": "2030-03-01",
        "end_date": "2030-03-10",
        "description": "",
        "why": "",
    })
    store.create_work({
        "name": "A Item",
        "start_date": "2030-01-05",
        "end_date": "2030-01-15",
        "description": "",
        "why": "",
    })
    store.create_work({
        "name": "B Item",
        "start_date": "2030-02-01",
        "end_date": None,
        "description": "",
        "why": "",
    })

    # Sort by start asc: A, B, C
    r = client.get("/?tab=work&wsort=start&worder=asc")
    html = r.get_data(as_text=True)
    order = _positions(html, ["A Item", "B Item", "C Item"])
    assert all(p >= 0 for p in order)
    assert order == sorted(order)

    # Sort by name asc: A, B, C
    r = client.get("/?tab=work&wsort=name&worder=asc")
    html = r.get_data(as_text=True)
    order = _positions(html, ["A Item", "B Item", "C Item"])
    assert all(p >= 0 for p in order)
    assert order == sorted(order)

    # Sort by end desc: items with end dates first in desc order (C then A); B (no end) last
    r = client.get("/?tab=work&wsort=end&worder=desc")
    html = r.get_data(as_text=True)
    order = _positions(html, ["C Item", "A Item", "B Item"])
    assert all(p >= 0 for p in order)
    assert order == sorted(order)
