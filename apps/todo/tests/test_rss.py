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


def test_rss_storage(client):
    store = client.application.extensions["store"]

    # 1. Create feeds
    feed = store.create_rss_feed({"url": "https://news.ycombinator.com/rss", "title": "Hacker News"})
    assert feed["id"] is not None
    assert feed["title"] == "Hacker News"
    assert feed["url"] == "https://news.ycombinator.com/rss"

    # 2. List feeds
    feeds = store.list_rss_feeds()
    assert len(feeds) == 1
    assert feeds[0]["id"] == feed["id"]

    # 3. RSS Item States
    # Initial state should be empty
    states = store.get_rss_item_states(feed_id=feed["id"])
    assert len(states) == 0

    # Update state (read=True)
    state = store.update_rss_item_state(user_id=None, feed_id=feed["id"], item_guid="item-1", read=True)
    assert state["read"] is True
    assert state["starred"] is False

    states = store.get_rss_item_states(feed_id=feed["id"])
    assert len(states) == 1
    assert states[0]["item_guid"] == "item-1"
    assert states[0]["read"] is True

    # Update state (starred=True)
    state2 = store.update_rss_item_state(user_id=None, feed_id=feed["id"], item_guid="item-1", starred=True)
    assert state2["starred"] is True
    assert state2["read"] is True

    # Update state (read=False, starred=False) -> should clean up/remove the state entry
    store.update_rss_item_state(user_id=None, feed_id=feed["id"], item_guid="item-1", read=False, starred=False)
    states = store.get_rss_item_states(feed_id=feed["id"])
    assert len(states) == 0

    # 4. Mark all as read
    store.mark_all_rss_items_read(user_id=None, feed_id=feed["id"], item_guids=["item-a", "item-b"])
    states = store.get_rss_item_states(feed_id=feed["id"])
    assert len(states) == 2
    assert all(s["read"] is True for s in states)

    # 5. Delete feed (cascading delete states)
    ok = store.delete_rss_feed(feed["id"])
    assert ok is True
    assert len(store.list_rss_feeds()) == 0
    assert len(store.get_rss_item_states(feed_id=feed["id"])) == 0


def test_rss_web_routes(client):
    # Subscribe to feed via POST (fake HN RSS)
    resp = client.post(
        "/rss/feed/add",
        data={"url": "https://news.ycombinator.com/rss"},
        follow_redirects=False
    )
    assert resp.status_code in (302, 303)

    store = client.application.extensions["store"]
    feeds = store.list_rss_feeds()
    assert len(feeds) == 1
    fid = feeds[0]["id"]

    # Toggle item state (read and star) via AJAX POST
    resp = client.post(
        "/rss/item/state",
        json={"feed_id": fid, "item_guid": "item-guid-123", "read": True, "starred": True}
    )
    assert resp.status_code == 200
    state = resp.get_json()["state"]
    assert state["read"] is True
    assert state["starred"] is True

    # Unsubscribe from feed
    resp = client.post(f"/rss/feed/{fid}/delete")
    assert resp.status_code in (302, 303)
    assert len(store.list_rss_feeds()) == 0
