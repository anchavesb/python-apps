import logging

from flask import Blueprint, current_app, jsonify, request, session

from .jwt_auth import validate_bearer_token
from .openapi_spec import OPENAPI_SPEC
from .storage import ValidationError

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__)


@api_bp.get("/openapi.json")
def openapi_spec():
    return jsonify(OPENAPI_SPEC)


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
        bearer_sub = bearer_user["sub"]
        bearer_email = bearer_user.get("email")
        logger.debug("auth via bearer token: sub=%s email=%s", bearer_sub, bearer_email)

        store_inst = store()
        # Reconcile cross-OIDC-app identity: if a user with the same email
        # already exists under a different sub (e.g. web login via 'notes' app
        # vs bearer token from 'dolores' app), use the existing user's ID.
        if hasattr(store_inst, "find_user_by_email") and bearer_email:
            existing = store_inst.find_user_by_email(bearer_email)
            if existing and existing.id != bearer_sub:
                logger.info(
                    "bearer sub=%s mapped to existing user sub=%s (same email=%s)",
                    bearer_sub, existing.id, bearer_email,
                )
                return existing.id

        # Ensure user exists in DB
        if hasattr(store_inst, "get_or_create_user"):
            store_inst.get_or_create_user(
                user_id=bearer_sub,
                email=bearer_email,
                name=bearer_user.get("name"),
            )
        return bearer_sub

    # Fall back to session cookie (web UI)
    user = session.get("user")
    if user:
        logger.debug("auth via session: sub=%s email=%s", user.get("sub"), user.get("email"))
        return user.get("sub")

    logger.debug("no auth: bearer token invalid and no session cookie")
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
