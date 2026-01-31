from flask import Blueprint, current_app, jsonify, request
from .storage import ValidationError

api_bp = Blueprint("api", __name__)


def store():
    return current_app.extensions["store"]


# ---- Todos ----
@api_bp.get("/todos")
def api_list_todos():
    return jsonify(store().list_todos())


@api_bp.post("/todos")
def api_create_todo():
    data = request.get_json(force=True, silent=True) or {}
    try:
        item = store().create_todo(data)
        return jsonify(item), 201
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400


@api_bp.get("/todos/<tid>")
def api_get_todo(tid):
    item = store().get_todo(tid)
    if not item:
        return jsonify({"error": "not found"}), 404
    return jsonify(item)


@api_bp.put("/todos/<tid>")
@api_bp.patch("/todos/<tid>")
def api_update_todo(tid):
    data = request.get_json(force=True, silent=True) or {}
    try:
        item = store().update_todo(tid, data)
        if not item:
            return jsonify({"error": "not found"}), 404
        return jsonify(item)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400


@api_bp.delete("/todos/<tid>")
def api_delete_todo(tid):
    ok = store().delete_todo(tid)
    return ("", 204) if ok else (jsonify({"error": "not found"}), 404)


@api_bp.post("/todos/<tid>/done")
def api_mark_done(tid):
    item = store().update_todo(tid, {"done": True})
    if not item:
        return jsonify({"error": "not found"}), 404
    return jsonify(item)


# ---- Notes ----
@api_bp.get("/notes")
def api_list_notes():
    return jsonify(store().list_notes())


@api_bp.post("/notes")
def api_create_note():
    data = request.get_json(force=True, silent=True) or {}
    try:
        item = store().create_note(data)
        return jsonify(item), 201
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400


@api_bp.get("/notes/<nid>")
def api_get_note(nid):
    item = store().get_note(nid)
    if not item:
        return jsonify({"error": "not found"}), 404
    return jsonify(item)


@api_bp.put("/notes/<nid>")
@api_bp.patch("/notes/<nid>")
def api_update_note(nid):
    data = request.get_json(force=True, silent=True) or {}
    try:
        item = store().update_note(nid, data)
        if not item:
            return jsonify({"error": "not found"}), 404
        return jsonify(item)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400


@api_bp.delete("/notes/<nid>")
def api_delete_note(nid):
    ok = store().delete_note(nid)
    return ("", 204) if ok else (jsonify({"error": "not found"}), 404)
