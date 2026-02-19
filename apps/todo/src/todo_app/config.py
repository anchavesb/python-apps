import os
from dataclasses import dataclass


def env(key: str, default: str) -> str:
    return os.getenv(key, default)


@dataclass
class Config:
    # Storage backend: "json" (default for dev) or "postgres" (production with multiuser)
    # When DATABASE_URL is set, defaults to "postgres"; otherwise defaults to "json"
    STORAGE_BACKEND: str = env("STORAGE_BACKEND", "postgres" if os.getenv("DATABASE_URL") else "json")

    # JSON file storage (used when STORAGE_BACKEND=json, single-user dev mode)
    DATA_FILE: str = env("DATA_FILE", os.path.abspath("data/appdata.json"))
    WAL_FILE: str = env("WAL_FILE", os.path.abspath("data/appdata.wal"))
    BACKUP_COUNT: int = int(env("BACKUP_COUNT", "10"))

    # PostgreSQL storage (used when STORAGE_BACKEND=postgres, multiuser production)
    DATABASE_URL: str = env("DATABASE_URL", "")

    SECRET_KEY: str = env("SECRET_KEY", "dev-secret-key")

    # UI
    APP_NAME: str = env("APP_NAME", "ToDo & Notes")
    PORT: int = int(env("PORT", "5000"))
    DEBUG: bool = env("DEBUG", "0") == "1"
    LOG_LEVEL: str = env("LOG_LEVEL", "INFO")

    # OIDC / Authentik
    OIDC_ENABLED: bool = env("OIDC_ENABLED", "0") == "1"
    OIDC_CLIENT_ID: str = env("OIDC_CLIENT_ID", "")
    OIDC_CLIENT_SECRET: str = env("OIDC_CLIENT_SECRET", "")
    OIDC_ISSUER: str = env("OIDC_ISSUER", "")  # e.g., https://auth.example.com/application/o/todo-app/
    OIDC_SCOPES: str = env("OIDC_SCOPES", "openid profile email")

    # Additional JWT issuers for mobile/API clients (comma-separated "issuer_url|client_id" pairs)
    OIDC_JWT_ISSUERS: str = env("OIDC_JWT_ISSUERS", "")
