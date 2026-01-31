import os
from flask import Flask
from .config import Config
from .storage import JsonStore

store: JsonStore | None = None


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    if test_config:
        app.config.update(test_config)

    # Ensure data directories exist
    os.makedirs(os.path.dirname(app.config["DATA_FILE"]), exist_ok=True)

    global store
    store = JsonStore(
        data_file=app.config["DATA_FILE"],
        backups=app.config["BACKUP_COUNT"],
        wal_file=app.config["WAL_FILE"],
    )
    store.load_or_recover()

    # Attach store to app for access in blueprints
    app.extensions["store"] = store

    from .api import api_bp
    from .web import web_bp

    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(web_bp)

    @app.route("/health")
    def health():
        ok, msg = store.validate_store()
        return ({"status": "ok", "message": msg}, 200) if ok else ({"status": "error", "message": msg}, 500)

    return app
