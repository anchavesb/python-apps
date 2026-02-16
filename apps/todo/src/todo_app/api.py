from flask import Blueprint, current_app, jsonify, request, session
from .storage import ValidationError
from .jwt_auth import validate_bearer_token

api_bp = Blueprint("api", __name__)


def store():
    return current_app.extensions["store"]


def get_user_from_bearer() -> dict | None:
    """Extract and validate a Bearer token from the Authorization header.

    Returns user info dict (sub, email, name, groups) or None.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]  # Strip "Bearer " prefix
    return validate_bearer_token(token)


def get_user_id():
    """Get user_id supporting both session auth (web) and bearer auth (mobile).

    Priority: Bearer token > session cookie.
    Returns user sub (str) or None for single-user JSON mode.
    """
    if not current_app.config.get("MULTIUSER"):
        return None

    # Try bearer token first (mobile/API clients)
    bearer_user = get_user_from_bearer()
    if bearer_user:
        # Ensure user exists in DB (same as session auth flow)
        store_inst = store()
        if hasattr(store_inst, "get_or_create_user"):
            store_inst.get_or_create_user(
                user_id=bearer_user["sub"],
                email=bearer_user.get("email"),
                name=bearer_user.get("name"),
            )
        return bearer_user["sub"]

    # Fall back to session cookie (web UI)
    user = session.get("user")
    if user:
        return user.get("sub")

    return None


def require_auth():
    """Return error response if auth is required but user not authenticated.

    Supports both session cookies and bearer tokens.
    """
    if not current_app.config.get("MULTIUSER"):
        return None

    # Check bearer token
    bearer_user = get_user_from_bearer()
    if bearer_user:
        return None

    # Check session
    if session.get("user"):
        return None

    return jsonify({"error": "authentication required"}), 401


# ---- Todos ----
@api_bp.get("/todos")
def api_list_todos():
    if err := require_auth():
        return err
    return jsonify(store().list_todos(user_id=get_user_id()))


@api_bp.post("/todos")
def api_create_todo():
    if err := require_auth():
        return err
    data = request.get_json(force=True, silent=True) or {}
    try:
        item = store().create_todo(data, user_id=get_user_id())
        return jsonify(item), 201
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400


@api_bp.get("/todos/<tid>")
def api_get_todo(tid):
    if err := require_auth():
        return err
    item = store().get_todo(tid, user_id=get_user_id())
    if not item:
        return jsonify({"error": "not found"}), 404
    return jsonify(item)


@api_bp.put("/todos/<tid>")
@api_bp.patch("/todos/<tid>")
def api_update_todo(tid):
    if err := require_auth():
        return err
    data = request.get_json(force=True, silent=True) or {}
    try:
        item = store().update_todo(tid, data, user_id=get_user_id())
        if not item:
            return jsonify({"error": "not found"}), 404
        return jsonify(item)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400


@api_bp.delete("/todos/<tid>")
def api_delete_todo(tid):
    if err := require_auth():
        return err
    ok = store().delete_todo(tid, user_id=get_user_id())
    return ("", 204) if ok else (jsonify({"error": "not found"}), 404)


@api_bp.post("/todos/<tid>/done")
def api_mark_done(tid):
    if err := require_auth():
        return err
    item = store().update_todo(tid, {"done": True}, user_id=get_user_id())
    if not item:
        return jsonify({"error": "not found"}), 404
    return jsonify(item)


# ---- Notes ----
@api_bp.get("/notes")
def api_list_notes():
    if err := require_auth():
        return err
    return jsonify(store().list_notes(user_id=get_user_id()))


@api_bp.post("/notes")
def api_create_note():
    if err := require_auth():
        return err
    data = request.get_json(force=True, silent=True) or {}
    try:
        item = store().create_note(data, user_id=get_user_id())
        return jsonify(item), 201
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400


@api_bp.get("/notes/<nid>")
def api_get_note(nid):
    if err := require_auth():
        return err
    item = store().get_note(nid, user_id=get_user_id())
    if not item:
        return jsonify({"error": "not found"}), 404
    return jsonify(item)


@api_bp.put("/notes/<nid>")
@api_bp.patch("/notes/<nid>")
def api_update_note(nid):
    if err := require_auth():
        return err
    data = request.get_json(force=True, silent=True) or {}
    try:
        item = store().update_note(nid, data, user_id=get_user_id())
        if not item:
            return jsonify({"error": "not found"}), 404
        return jsonify(item)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400


@api_bp.delete("/notes/<nid>")
def api_delete_note(nid):
    if err := require_auth():
        return err
    ok = store().delete_note(nid, user_id=get_user_id())
    return ("", 204) if ok else (jsonify({"error": "not found"}), 404)


# ---- Work Items ----
@api_bp.get("/work")
def api_list_work():
    if err := require_auth():
        return err
    return jsonify(store().list_work(user_id=get_user_id()))


@api_bp.post("/work")
def api_create_work():
    if err := require_auth():
        return err
    data = request.get_json(force=True, silent=True) or {}
    try:
        item = store().create_work(data, user_id=get_user_id())
        return jsonify(item), 201
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400


@api_bp.get("/work/<wid>")
def api_get_work(wid):
    if err := require_auth():
        return err
    item = store().get_work(wid, user_id=get_user_id())
    if not item:
        return jsonify({"error": "not found"}), 404
    return jsonify(item)


@api_bp.put("/work/<wid>")
@api_bp.patch("/work/<wid>")
def api_update_work(wid):
    if err := require_auth():
        return err
    data = request.get_json(force=True, silent=True) or {}
    try:
        item = store().update_work(wid, data, user_id=get_user_id())
        if not item:
            return jsonify({"error": "not found"}), 404
        return jsonify(item)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400


@api_bp.delete("/work/<wid>")
def api_delete_work(wid):
    if err := require_auth():
        return err
    ok = store().delete_work(wid, user_id=get_user_id())
    return ("", 204) if ok else (jsonify({"error": "not found"}), 404)
