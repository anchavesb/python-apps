from __future__ import annotations

import concurrent.futures
import re
from datetime import date
from html import escape as html_escape

import feedparser
import requests
from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from .auth import login_required
from .storage import PRIORITIES, ValidationError


def get_user_id():
    """Get user_id for multiuser mode, or None for single-user JSON mode."""
    if current_app.config.get("MULTIUSER"):
        user = session.get("user")
        if user:
            return user.get("sub")
    return None

# Optional Markdown/sanitizer; fall back gracefully if unavailable
try:
    import bleach  # type: ignore
    import markdown as md  # type: ignore
    HAVE_MD = True
except Exception:
    md = None  # type: ignore
    bleach = None  # type: ignore
    HAVE_MD = False

web_bp = Blueprint("web", __name__)

PRIORITY_ORDER = {"urgent": 0, "high": 1, "medium": 2, "low": 3}

if HAVE_MD:
    ALLOWED_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
        "p", "pre", "code", "hr", "br",
        "h1", "h2", "h3", "blockquote",
    ]
    ALLOWED_ATTRS = {
        **bleach.sanitizer.ALLOWED_ATTRIBUTES,
        "a": ["href", "title", "rel", "target"],
    }
else:
    ALLOWED_TAGS = []
    ALLOWED_ATTRS = {}


def store():
    return current_app.extensions["store"]


def parse_tags(form):
    # Expect tags as key=value lines (textarea) or via individual fields
    tags = {}
    raw = form.get("tags_text", "").strip()
    for line in raw.splitlines():
        if not line.strip():
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            tags[k.strip()] = v.strip()
    # Ensure category and priority come from dedicated fields if provided
    if form.get("category"):
        tags["category"] = form.get("category").strip()
    if form.get("priority"):
        tags["priority"] = form.get("priority").strip()
    return tags


def render_markdown_safe(text: str | None) -> str:
    if not text:
        return ""
    if HAVE_MD:
        html = md.markdown(text, extensions=["extra", "sane_lists", "smarty"])  # type: ignore
        html = bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS)  # type: ignore
        html = bleach.linkify(html)  # type: ignore
        return html

    # Fallback: very small subset renderer with escaping first
    s = html_escape(text)
    # Code blocks ```
    s = re.sub(r"```(.*?)```", r"<pre><code>\1</code></pre>", s, flags=re.S)
    # Inline code `code`
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    # Bold **text** and Italic *text*
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", s)
    # Links: bare URLs
    url_re = r"(https?://[\w\-./?%&=#:+~]+)"
    s = re.sub(url_re, r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>', s)
    # Paragraphs: split on blank lines
    parts = [p.strip() for p in re.split(r"\n\s*\n", s) if p.strip()]
    html = "".join(f"<p>{p.replace('\n', '<br>')}</p>" for p in parts)
    return html


def fetch_feed_data(feed_id, url, title, user_id, item_states):
    try:
        r = requests.get(url, timeout=5, headers={"User-Agent": "DoloresRSS/1.0"})
        if r.status_code == 200:
            parsed = feedparser.parse(r.content)
            entries = []
            for entry in parsed.entries:
                guid = entry.get("id") or entry.get("link") or entry.get("title")
                if not guid:
                    continue
                state = item_states.get(guid, {})

                content = ""
                if "content" in entry:
                    content = entry.content[0].value
                elif "summary" in entry:
                    content = entry.summary
                elif "description" in entry:
                    content = entry.description

                pub_date = entry.get("published") or entry.get("updated") or ""
                pub_parsed = entry.get("published_parsed") or entry.get("updated_parsed")

                # Sanitize HTML safely
                if HAVE_MD:
                    content_clean = bleach.clean(content, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS)
                else:
                    content_clean = content

                entries.append({
                    "guid": guid,
                    "title": entry.get("title") or "Untitled Article",
                    "link": entry.get("link") or "",
                    "pub_date": pub_date,
                    "pub_parsed": pub_parsed,
                    "content": content_clean,
                    "read": state.get("read", False),
                    "starred": state.get("starred", False),
                    "feed_title": title,
                    "feed_id": feed_id,
                })
            return feed_id, entries, None
    except Exception as e:
        return feed_id, [], str(e)
    return feed_id, [], "Could not fetch feed"


@web_bp.route("/")
@login_required
def index():
    q = request.args.get("q", "").lower()
    priority = request.args.get("priority")
    category = request.args.get("category")
    status = request.args.get("status", "open")  # open|done|all (default=open)
    sort = request.args.get("sort", "default")  # default|due_date|priority|status|updated_at|created_at|title
    order = request.args.get("order", "asc")  # asc|desc
    tab = request.args.get("tab", "todos")  # todos|notes|rss
    rss_filter = request.args.get("rss_filter", "all")  # all|starred|<feed_id>

    user_id = get_user_id()
    todos = store().list_todos(user_id=user_id)
    notes = store().list_notes(user_id=user_id)

    # RSS data loading
    feeds = store().list_rss_feeds(user_id=user_id)
    item_states_list = store().get_rss_item_states(user_id=user_id)
    item_states = {s["item_guid"]: s for s in item_states_list}

    # Parallel RSS fetching if on the rss tab
    rss_items = []
    feed_entries_map = {}
    feed_errors = {}
    if tab == "rss" and feeds:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(feeds), 10)) as executor:
            futures = [
                executor.submit(fetch_feed_data, f["id"], f["url"], f["title"], user_id, item_states)
                for f in feeds
            ]
            for fut in concurrent.futures.as_completed(futures):
                fid, entries, err = fut.result()
                if err:
                    feed_errors[fid] = err
                feed_entries_map[fid] = entries
                rss_items.extend(entries)

        # Sort RSS items descending by parsed date
        rss_items.sort(
            key=lambda x: x.get("pub_parsed") or (0, 0, 0, 0, 0, 0, 0, 0, 0),
            reverse=True
        )

        # Filter RSS items
        if rss_filter == "starred":
            rss_items = [it for it in rss_items if it["starred"]]
        elif rss_filter != "all":
            rss_items = [it for it in rss_items if it["feed_id"] == rss_filter]

        # Calculate dynamic unread counts per feed
        for f in feeds:
            entries = feed_entries_map.get(f["id"], [])
            f["unread_count"] = sum(1 for e in entries if not e["read"])
    else:
        for f in feeds:
            f["unread_count"] = 0

    # Todos and notes filtering
    def match_item(it):
        text = (it.get("title", "") + " " + (it.get("description") or it.get("note") or "")).lower()
        if q and q not in text:
            return False
        if priority and it.get("tags", {}).get("priority") != priority:
            return False
        if category and it.get("tags", {}).get("category") != category:
            return False
        if status in ("open", "done") and "done" in it:
            if status == "open" and it["done"]:
                return False
            if status == "done" and not it["done"]:
                return False
        return True

    todos = [t for t in todos if match_item(t)]
    notes = [n for n in notes if match_item(n)]

    # Compute due date color coding for todos
    today = date.today()
    for t in todos:
        dd = t.get("due_date")
        color = "text-success"
        label = None
        if dd:
            try:
                d = date.fromisoformat(str(dd)[:10])
                delta = (d - today).days
                if delta >= 2:
                    color = "text-success"
                elif delta == 1:
                    color = "text-warning"
                else:  # due today or overdue
                    color = "text-danger"
                label = dd
            except Exception:
                # Fallback if parsing fails
                color = "text-secondary"
                label = dd
        else:
            label = "No due date"
            color = "text-success"
        t["_due_color"] = color
        t["_due_label"] = label

    # Render Markdown for notes safely
    for n in notes:
        n["_note_html"] = render_markdown_safe(n.get("note"))

    # Sorting helpers
    def todo_sort_key(t):
        # derive fields
        pr = t.get("tags", {}).get("priority") or "low"
        pr_rank = PRIORITY_ORDER.get(pr, 99)
        dd = t.get("due_date")
        dd_key = (date.max)  # default large
        try:
            if dd:
                dd_key = date.fromisoformat(str(dd)[:10])
        except Exception:
            pass
        status_rank = 0 if not t.get("done") else 1  # open first
        title = (t.get("title") or "").lower()
        created = t.get("created_at") or ""
        updated = t.get("updated_at") or ""

        if sort == "due_date":
            key = (dd_key, pr_rank, status_rank, title)
        elif sort == "priority":
            key = (pr_rank, dd_key, status_rank, title)
        elif sort == "status":
            key = (status_rank, dd_key, pr_rank, title)
        elif sort == "updated_at":
            key = (updated, dd_key, pr_rank, status_rank, title)
        elif sort == "created_at":
            key = (created, dd_key, pr_rank, status_rank, title)
        elif sort == "title":
            key = (title, dd_key, pr_rank, status_rank)
        else:  # default combined
            key = (status_rank, dd_key, pr_rank, title)
        return key

    def note_sort_key(n):
        pr = n.get("tags", {}).get("priority") or "low"
        pr_rank = PRIORITY_ORDER.get(pr, 99)
        title = (n.get("title") or "").lower()
        created = n.get("created_at") or ""
        updated = n.get("updated_at") or ""
        if sort == "priority":
            key = (pr_rank, title)
        elif sort == "updated_at":
            key = (updated, pr_rank, title)
        elif sort == "created_at":
            key = (created, pr_rank, title)
        elif sort == "title":
            key = (title, pr_rank)
        else:
            key = (updated, pr_rank, title)  # default: recent first (we may reverse)
        return key

    reverse = (order == "desc")
    notes_reverse = True if sort == "default" else reverse

    todos.sort(key=todo_sort_key, reverse=reverse)
    notes.sort(key=note_sort_key, reverse=notes_reverse)

    categories = sorted(
        ({t["tags"].get("category") for t in todos if t.get("tags") and t["tags"].get("category")} |
         {n["tags"].get("category") for n in notes if n.get("tags") and n["tags"].get("category")})
    )

    return render_template(
        "index.html",
        todos=todos,
        notes=notes,
        priorities=sorted(PRIORITIES),
        q=q,
        priority=priority,
        category=category,
        status=status,
        sort=sort,
        order=order,
        categories=[c for c in categories if c],
        tab=tab,
        feeds=feeds,
        rss_items=rss_items,
        rss_filter=rss_filter,
        feed_errors=feed_errors,
    )


@web_bp.route("/todos/new", methods=["GET", "POST"])
@login_required
def new_todo():
    if request.method == "POST":
        data = {
            "title": request.form.get("title", "").strip(),
            "description": request.form.get("description"),
            "due_date": request.form.get("due_date") or None,
            "done": bool(request.form.get("done")),
            "tags": parse_tags(request.form),
        }
        try:
            store().create_todo(data, user_id=get_user_id())
            flash("To-do created", "success")
            return redirect(url_for("web.index"))
        except ValidationError as e:
            flash(str(e), "danger")
    return render_template("todo_form.html", priorities=sorted(PRIORITIES), item=None)


@web_bp.route("/todos/<tid>/edit", methods=["GET", "POST"])
@login_required
def edit_todo(tid):
    user_id = get_user_id()
    item = store().get_todo(tid, user_id=user_id)
    if not item:
        flash("To-do not found", "warning")
        return redirect(url_for("web.index"))
    if request.method == "POST":
        data = {
            "title": request.form.get("title", item["title"]).strip(),
            "description": request.form.get("description"),
            "due_date": request.form.get("due_date") or None,
            "done": bool(request.form.get("done")),
            "tags": parse_tags(request.form),
        }
        try:
            store().update_todo(tid, data, user_id=user_id)
            flash("To-do updated", "success")
            return redirect(url_for("web.index"))
        except ValidationError as e:
            flash(str(e), "danger")
    tags_text = "\n".join(f"{k}={v}" for k, v in (item.get("tags") or {}).items() if k not in ("category", "priority"))
    return render_template("todo_form.html", priorities=sorted(PRIORITIES), item=item, tags_text=tags_text)


@web_bp.post("/todos/<tid>/delete")
@login_required
def delete_todo(tid):
    store().delete_todo(tid, user_id=get_user_id())
    flash("To-do deleted", "info")
    return redirect(url_for("web.index"))


@web_bp.post("/todos/<tid>/done")
@login_required
def done_todo(tid):
    store().update_todo(tid, {"done": True}, user_id=get_user_id())
    flash("Marked as done", "success")
    return redirect(url_for("web.index"))


@web_bp.route("/notes/new", methods=["GET", "POST"])
@login_required
def new_note():
    if request.method == "POST":
        data = {
            "title": request.form.get("title", "").strip(),
            "note": request.form.get("note"),
            "tags": parse_tags(request.form),
        }
        try:
            store().create_note(data, user_id=get_user_id())
            flash("Note created", "success")
            return redirect(url_for("web.index", tab="notes"))
        except ValidationError as e:
            flash(str(e), "danger")
    return render_template("note_form.html", priorities=sorted(PRIORITIES), item=None)


@web_bp.route("/notes/<nid>/edit", methods=["GET", "POST"])
@login_required
def edit_note(nid):
    user_id = get_user_id()
    item = store().get_note(nid, user_id=user_id)
    if not item:
        flash("Note not found", "warning")
        return redirect(url_for("web.index", tab="notes"))
    if request.method == "POST":
        data = {
            "title": request.form.get("title", item["title"]).strip(),
            "note": request.form.get("note"),
            "tags": parse_tags(request.form),
        }
        try:
            store().update_note(nid, data, user_id=user_id)
            flash("Note updated", "success")
            return redirect(url_for("web.index", tab="notes"))
        except ValidationError as e:
            flash(str(e), "danger")
    tags_text = "\n".join(f"{k}={v}" for k, v in (item.get("tags") or {}).items() if k not in ("category", "priority"))
    return render_template("note_form.html", priorities=sorted(PRIORITIES), item=item, tags_text=tags_text)


@web_bp.post("/notes/<nid>/delete")
@login_required
def delete_note(nid):
    store().delete_note(nid, user_id=get_user_id())
    flash("Note deleted", "info")
    return redirect(url_for("web.index", tab="notes"))

@web_bp.route("/rss/feed/add", methods=["POST"])
@login_required
def add_rss_feed():
    url = request.form.get("url", "").strip()
    if not url:
        flash("Feed URL is required", "danger")
        return redirect(url_for("web.index", tab="rss"))

    # Fetch feed title
    try:
        r = requests.get(url, timeout=5, headers={"User-Agent": "DoloresRSS/1.0"})
        parsed = feedparser.parse(r.content)
        title = parsed.feed.get("title") or "Unnamed Feed"
    except Exception:
        title = "Unnamed Feed"

    try:
        store().create_rss_feed({"url": url, "title": title}, user_id=get_user_id())
        flash(f"Subscribed to {title}", "success")
    except Exception as e:
        flash(f"Error subscribing: {str(e)}", "danger")

    return redirect(url_for("web.index", tab="rss"))


@web_bp.route("/rss/feed/<feed_id>/delete", methods=["POST"])
@login_required
def delete_rss_feed(feed_id):
    try:
        store().delete_rss_feed(feed_id, user_id=get_user_id())
        flash("Unsubscribed from feed", "info")
    except Exception as e:
        flash(f"Error unsubscribing: {str(e)}", "danger")
    return redirect(url_for("web.index", tab="rss"))


@web_bp.route("/rss/item/state", methods=["POST"])
@login_required
def update_item_state():
    data = request.get_json() or {}
    feed_id = data.get("feed_id")
    item_guid = data.get("item_guid")
    read = data.get("read")
    starred = data.get("starred")

    if not feed_id or not item_guid:
        return jsonify({"error": "Missing feed_id or item_guid"}), 400

    try:
        state = store().update_rss_item_state(
            user_id=get_user_id(),
            feed_id=feed_id,
            item_guid=item_guid,
            read=read,
            starred=starred
        )
        return jsonify({"status": "ok", "state": state})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@web_bp.route("/rss/feed/<feed_id>/mark-all-read", methods=["POST"])
@login_required
def mark_all_read(feed_id):
    user_id = get_user_id()
    if feed_id == "all":
        feeds = store().list_rss_feeds(user_id=user_id)
    else:
        feeds = [f for f in store().list_rss_feeds(user_id=user_id) if f["id"] == feed_id]

    for f in feeds:
        try:
            r = requests.get(f["url"], timeout=5, headers={"User-Agent": "DoloresRSS/1.0"})
            parsed = feedparser.parse(r.content)
            guids = []
            for entry in parsed.entries:
                guid = entry.get("id") or entry.get("link") or entry.get("title")
                if guid:
                    guids.append(guid)
            store().mark_all_rss_items_read(user_id, f["id"], guids)
        except Exception:
            pass

    flash("Marked items as read", "success")
    return redirect(url_for("web.index", tab="rss"))
