import logging
import os

from flask import Flask
from .config import Config
from .storage import JsonStore

store: JsonStore | None = None


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    # Configure logging
    log_level = getattr(logging, app.config.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if test_config:
        app.config.update(test_config)

    global store
    backend = app.config.get("STORAGE_BACKEND", "json")

    if backend == "postgres":
        # PostgreSQL with multiuser support
        from .db_store import PostgresStore
        database_url = app.config["DATABASE_URL"]
        if not database_url:
            raise ValueError("DATABASE_URL is required when STORAGE_BACKEND=postgres")
        store = PostgresStore(database_url)
        store.init_db()
        app.config["MULTIUSER"] = True
    else:
        # JSON file storage (dev mode, single-user)
        os.makedirs(os.path.dirname(app.config["DATA_FILE"]), exist_ok=True)
        store = JsonStore(
            data_file=app.config["DATA_FILE"],
            backups=app.config["BACKUP_COUNT"],
            wal_file=app.config["WAL_FILE"],
        )
        store.load_or_recover()
        app.config["MULTIUSER"] = False

    # Attach store to app for access in blueprints
    app.extensions["store"] = store

    # Initialize OIDC authentication
    from .auth import auth_bp, init_oauth
    init_oauth(app)
    app.register_blueprint(auth_bp, url_prefix="/auth")

    # Initialize JWT bearer token validation (for mobile/API clients)
    from .jwt_auth import init_jwt_auth
    init_jwt_auth(app)

    from .api import api_bp
    from .web import web_bp

    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(web_bp)

    @app.route("/health")
    def health():
        ok, msg = store.validate_store()
        return ({"status": "ok", "message": msg}, 200) if ok else ({"status": "error", "message": msg}, 500)

    return app
