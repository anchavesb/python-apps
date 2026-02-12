from flask import Blueprint, current_app, jsonify, request, session
from .storage import ValidationError

api_bp = Blueprint("api", __name__)


def store():
    return current_app.extensions["store"]


def get_user_id():
    """Get user_id for multiuser mode, or None for single-user JSON mode."""
    if current_app.config.get("MULTIUSER"):
        user = session.get("user")
        if not user:
            return None
        return user.get("sub")
    return None


def require_auth():
    """Return error response if multiuser mode requires auth but user not logged in."""
    if current_app.config.get("MULTIUSER") and not get_user_id():
        return jsonify({"error": "authentication required"}), 401
    return None


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
