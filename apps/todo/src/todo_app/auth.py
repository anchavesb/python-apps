"""OIDC authentication blueprint for Authentik integration."""
from functools import wraps
from flask import Blueprint, current_app, redirect, url_for, session, request, flash
from authlib.integrations.flask_client import OAuth

auth_bp = Blueprint("auth", __name__)
oauth = OAuth()


def init_oauth(app):
    """Initialize OAuth with Authentik OIDC configuration."""
    if not app.config.get("OIDC_ENABLED"):
        return

    oauth.init_app(app)

    # Authentik OIDC discovery URL
    issuer = app.config["OIDC_ISSUER"].rstrip("/")

    oauth.register(
        name="authentik",
        client_id=app.config["OIDC_CLIENT_ID"],
        client_secret=app.config["OIDC_CLIENT_SECRET"],
        server_metadata_url=f"{issuer}/.well-known/openid-configuration",
        client_kwargs={"scope": app.config["OIDC_SCOPES"]},
    )


def login_required(f):
    """Decorator to require authentication when OIDC is enabled."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_app.config.get("OIDC_ENABLED"):
            return f(*args, **kwargs)

        if "user" not in session:
            session["next_url"] = request.url
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function


def get_current_user():
    """Get current user from session."""
    return session.get("user")


@auth_bp.route("/login")
def login():
    if not current_app.config.get("OIDC_ENABLED"):
        flash("Authentication is not enabled", "warning")
        return redirect(url_for("web.index"))

    redirect_uri = url_for("auth.callback", _external=True)
    return oauth.authentik.authorize_redirect(redirect_uri)


@auth_bp.route("/callback")
def callback():
    if not current_app.config.get("OIDC_ENABLED"):
        return redirect(url_for("web.index"))

    try:
        token = oauth.authentik.authorize_access_token()
        userinfo = token.get("userinfo")

        if userinfo:
            session["user"] = {
                "sub": userinfo.get("sub"),
                "email": userinfo.get("email"),
                "name": userinfo.get("name") or userinfo.get("preferred_username"),
                "groups": userinfo.get("groups", []),
            }
            flash(f"Welcome, {session['user']['name']}!", "success")

        next_url = session.pop("next_url", None)
        return redirect(next_url or url_for("web.index"))

    except Exception as e:
        current_app.logger.error(f"OIDC callback error: {e}")
        flash("Authentication failed. Please try again.", "danger")
        return redirect(url_for("web.index"))


@auth_bp.route("/logout")
def logout():
    session.pop("user", None)
    flash("You have been logged out.", "info")

    # Optionally redirect to Authentik's logout endpoint
    if current_app.config.get("OIDC_ENABLED"):
        issuer = current_app.config["OIDC_ISSUER"].rstrip("/")
        # Authentik end session endpoint
        return redirect(f"{issuer}/end-session/")

    return redirect(url_for("web.index"))
