from __future__ import annotations
from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash
from datetime import date
from .storage import PRIORITIES, ValidationError

# Optional Markdown/sanitizer; fall back gracefully if unavailable
try:
    import markdown as md  # type: ignore
    import bleach  # type: ignore
    HAVE_MD = True
except Exception:
    md = None  # type: ignore
    bleach = None  # type: ignore
    HAVE_MD = False

import re
from html import escape as html_escape

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


@web_bp.route("/")
def index():
    q = request.args.get("q", "").lower()
    priority = request.args.get("priority")
    category = request.args.get("category")
    status = request.args.get("status", "open")  # open|done|all (default=open)
    sort = request.args.get("sort", "default")  # default|due_date|priority|status|updated_at|created_at|title
    order = request.args.get("order", "asc")  # asc|desc
    tab = request.args.get("tab", "todos")  # todos|notes|work
    wq = request.args.get("wq", "").lower()
    ws_from = request.args.get("ws_from")
    ws_to = request.args.get("ws_to")
    wsort = request.args.get("wsort", "start")
    worder = request.args.get("worder", "asc")

    todos = store().list_todos()
    notes = store().list_notes()
    work_items = store().list_work()

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
    todos.sort(key=todo_sort_key, reverse=reverse)
    notes.sort(key=note_sort_key, reverse=(order == "desc"))

    categories = sorted(
        ({t["tags"].get("category") for t in todos if t.get("tags") and t["tags"].get("category")} |
         {n["tags"].get("category") for n in notes if n.get("tags") and n["tags"].get("category")})
    )

    # Work filtering
    def match_work(w):
        text = (w.get("name", "") + " " + (w.get("description") or "") + " " + (w.get("why") or "")).lower()
        if wq and wq not in text:
            return False
        try:
            sd = date.fromisoformat(str(w.get("start_date") or "")[:10])
        except Exception:
            sd = None
        try:
            ed = date.fromisoformat(str(w.get("end_date") or "")[:10]) if w.get("end_date") else None
        except Exception:
            ed = None
        if ws_from:
            try:
                f = date.fromisoformat(ws_from[:10])
                if sd and sd < f:
                    return False
            except Exception:
                pass
        if ws_to:
            try:
                tdate = date.fromisoformat(ws_to[:10])
                if ed and ed > tdate:
                    return False
                if ed is None and sd and sd > tdate:
                    return False
            except Exception:
                pass
        return True

    work_items = [w for w in work_items if match_work(w)]

    def work_sort_key(w):
        name_key = (w.get("name") or "").lower()
        s = (w.get("start_date") or "")
        e = (w.get("end_date") or "")
        u = (w.get("updated_at") or "")
        if wsort == "end":
            key = (e, s, name_key)
        elif wsort == "updated":
            key = (u, s, name_key)
        elif wsort == "name":
            key = (name_key, s)
        else:
            key = (s, e, name_key)
        return key

    work_items.sort(key=work_sort_key, reverse=(worder == "desc"))

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
        work_items=work_items,
        wq=wq,
        ws_from=ws_from,
        ws_to=ws_to,
        wsort=wsort,
        worder=worder,
    )


@web_bp.route("/todos/new", methods=["GET", "POST"])
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
            store().create_todo(data)
            flash("To-do created", "success")
            return redirect(url_for("web.index"))
        except ValidationError as e:
            flash(str(e), "danger")
    return render_template("todo_form.html", priorities=sorted(PRIORITIES), item=None)


@web_bp.route("/todos/<tid>/edit", methods=["GET", "POST"])
def edit_todo(tid):
    item = store().get_todo(tid)
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
            store().update_todo(tid, data)
            flash("To-do updated", "success")
            return redirect(url_for("web.index"))
        except ValidationError as e:
            flash(str(e), "danger")
    tags_text = "\n".join(f"{k}={v}" for k, v in (item.get("tags") or {}).items() if k not in ("category", "priority"))
    return render_template("todo_form.html", priorities=sorted(PRIORITIES), item=item, tags_text=tags_text)


@web_bp.post("/todos/<tid>/delete")
def delete_todo(tid):
    store().delete_todo(tid)
    flash("To-do deleted", "info")
    return redirect(url_for("web.index"))


@web_bp.post("/todos/<tid>/done")
def done_todo(tid):
    store().update_todo(tid, {"done": True})
    flash("Marked as done", "success")
    return redirect(url_for("web.index"))


@web_bp.route("/notes/new", methods=["GET", "POST"])
def new_note():
    if request.method == "POST":
        data = {
            "title": request.form.get("title", "").strip(),
            "note": request.form.get("note"),
            "tags": parse_tags(request.form),
        }
        try:
            store().create_note(data)
            flash("Note created", "success")
            return redirect(url_for("web.index"))
        except ValidationError as e:
            flash(str(e), "danger")
    return render_template("note_form.html", priorities=sorted(PRIORITIES), item=None)


@web_bp.route("/notes/<nid>/edit", methods=["GET", "POST"])
def edit_note(nid):
    item = store().get_note(nid)
    if not item:
        flash("Note not found", "warning")
        return redirect(url_for("web.index"))
    if request.method == "POST":
        data = {
            "title": request.form.get("title", item["title"]).strip(),
            "note": request.form.get("note"),
            "tags": parse_tags(request.form),
        }
        try:
            store().update_note(nid, data)
            flash("Note updated", "success")
            return redirect(url_for("web.index"))
        except ValidationError as e:
            flash(str(e), "danger")
    tags_text = "\n".join(f"{k}={v}" for k, v in (item.get("tags") or {}).items() if k not in ("category", "priority"))
    return render_template("note_form.html", priorities=sorted(PRIORITIES), item=item, tags_text=tags_text)


@web_bp.post("/notes/<nid>/delete")
def delete_note(nid):
    store().delete_note(nid)
    flash("Note deleted", "info")
    return redirect(url_for("web.index"))

@web_bp.route("/work/new", methods=["GET", "POST"])
def new_work():
    if request.method == "POST":
        data = {
            "name": request.form.get("name", "").strip(),
            "start_date": request.form.get("start_date") or "",
            "end_date": request.form.get("end_date") or None,
            "description": request.form.get("description"),
            "why": request.form.get("why"),
        }
        try:
            store().create_work(data)
            flash("Work item created", "success")
            return redirect(url_for("web.index", tab="work"))
        except ValidationError as e:
            flash(str(e), "danger")
    return render_template("work_form.html", item=None)


@web_bp.route("/work/<wid>/edit", methods=["GET", "POST"])
def edit_work(wid):
    item = store().get_work(wid)
    if not item:
        flash("Work item not found", "warning")
        return redirect(url_for("web.index", tab="work"))
    if request.method == "POST":
        data = {
            "name": request.form.get("name", item["name"]).strip(),
            "start_date": request.form.get("start_date") or item["start_date"],
            "end_date": request.form.get("end_date") or None,
            "description": request.form.get("description"),
            "why": request.form.get("why"),
        }
        try:
            store().update_work(wid, data)
            flash("Work item updated", "success")
            return redirect(url_for("web.index", tab="work"))
        except ValidationError as e:
            flash(str(e), "danger")
    return render_template("work_form.html", item=item)


@web_bp.post("/work/<wid>/delete")
def delete_work(wid):
    store().delete_work(wid)
    flash("Work item deleted", "info")
    return redirect(url_for("web.index", tab="work"))
