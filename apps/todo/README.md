# ToDo & Notes Flask App

A web app for managing to-dos and notes with support for two storage backends:
- **JSON file** (single-user, dev mode): File persistence with rolling backups and WAL-based recovery
- **PostgreSQL** (multiuser, production): Full multiuser support with user isolation via OIDC

Includes a minimal JSON API and a Bootstrap-based modern UI.

## Quickstart (Development - JSON Backend)

Requirements: Python 3.11+ recommended

From the monorepo root:

```bash
cd /Users/achaves/repos/personal/python-apps
scripts/dev.sh                # sets up .venv and installs apps in editable mode
make run-todo                 # run via console entry point (todo-app)
# or during development
make run-todo-dev             # run directly from source
```

The app runs on http://localhost:5000/ by default using JSON file storage.

### Environment Variables (JSON Mode)

- STORAGE_BACKEND (default: "json" when DATABASE_URL not set)
- DATA_FILE (default: ./data/appdata.json)
- WAL_FILE (default: ./data/appdata.wal)
- BACKUP_COUNT (default: 10)
- PORT (default: 5000)
- DEBUG (default: 0; set DEBUG=1 to enable)

## PostgreSQL Backend (Production - Multiuser)

For production deployments with multiuser support, set `DATABASE_URL` to automatically enable PostgreSQL:

```bash
DATABASE_URL="postgresql://user:pass@localhost:5432/todo" make run-todo
```

Or explicitly set the backend:

```bash
STORAGE_BACKEND=postgres DATABASE_URL="postgresql://..." make run-todo
```

### Environment Variables (PostgreSQL Mode)

- STORAGE_BACKEND (default: "postgres" when DATABASE_URL is set)
- DATABASE_URL (required): PostgreSQL connection string
- OIDC_ENABLED (default: 0): Set to 1 to enable OIDC authentication
- OIDC_ISSUER: OIDC provider URL (e.g., https://auth.example.com/application/o/todo/)
- OIDC_CLIENT_ID: OAuth client ID
- OIDC_CLIENT_SECRET: OAuth client secret
- OIDC_SCOPES (default: "openid profile email")

### Database Schema

Tables are created automatically on startup:
- `users`: User accounts (keyed by OIDC sub claim)
- `todos`: To-do items with user isolation
- `notes`: Notes with user isolation
- `work_items`: Work items with user isolation

## Container image (GHCR)

Images are built and published by CI to GitHub Container Registry when tests pass on pushes to `main` or tags.

### Development (JSON file storage)

```bash
docker pull ghcr.io/OWNER/todo:latest

docker run --rm -p 5000:5000 \
  -e PORT=5000 \
  -e DEBUG=0 \
  -v "$(pwd)/../../data:/app/data" \
  ghcr.io/OWNER/todo:latest
```

### Production (PostgreSQL + OIDC)

```bash
docker run --rm -p 5000:5000 \
  -e DATABASE_URL="postgresql://user:pass@db:5432/todo" \
  -e OIDC_ENABLED=1 \
  -e OIDC_ISSUER="https://auth.example.com/application/o/todo/" \
  -e OIDC_CLIENT_ID="your-client-id" \
  -e OIDC_CLIENT_SECRET="your-client-secret" \
  -e SECRET_KEY="your-secure-secret-key" \
  ghcr.io/OWNER/todo:latest
```

## JSON API

- GET /api/todos
- POST /api/todos
  - JSON: { title, description?, tags{category,priority,...}, done?, due_date? }
- GET /api/todos/<id>
- PATCH/PUT /api/todos/<id>
- DELETE /api/todos/<id>
- POST /api/todos/<id>/done

- GET /api/notes
- POST /api/notes
  - JSON: { title, note?, tags{category,priority,...} }
- GET /api/notes/<id>
- PATCH/PUT /api/notes/<id>
- DELETE /api/notes/<id>

Responses are JSON. Errors return {"error": "message"} with appropriate status.

**Note:** In multiuser mode (PostgreSQL), API endpoints require authentication and return only the current user's data.

## Architecture

- src/todo_app/__init__.py: Flask app factory; registers blueprints; health endpoint
- src/todo_app/config.py: Configuration via env with defaults
- src/todo_app/storage.py: JsonStore handles JSON file persistence
  - Validation of models
  - Atomic writes and backup rotation
  - WAL append and replay
  - CRUD for todos, notes, work items
- src/todo_app/models.py: SQLAlchemy models for PostgreSQL
- src/todo_app/db_store.py: PostgresStore handles PostgreSQL persistence with multiuser
- src/todo_app/auth.py: OIDC authentication with Authentik
- src/todo_app/api.py: JSON API endpoints
- src/todo_app/web.py: HTML routes and forms
- src/todo_app/templates/: Jinja templates using Bootstrap
- src/todo_app/static/: CSS
- src/todo_app/wsgi.py: WSGI module for gunicorn
- apps/todo/run.py: dev entrypoint to run from source
- apps/todo/tests/: pytest suite

## Kubernetes Deployment

The app is deployed to Kubernetes using CloudNativePG for PostgreSQL. See the infrastructure repo for:
- `postgres.yaml`: CNPG Cluster definition with S3 backups
- `deployment.yaml`: App deployment with DATABASE_URL from CNPG secret
- `config.yaml`: ConfigMap with STORAGE_BACKEND=postgres

The CNPG operator automatically creates a secret `todo-db-app` with the connection URI.

## Data migration from old repo (optional)

If you had existing data in the old repository, copy it into the monorepo:

```bash
OLD=/Users/achaves/repos/personal/todo/data
NEW=/Users/achaves/repos/personal/python-apps/data
mkdir -p "$NEW"
cp -v "$OLD/appdata.json" "$NEW/appdata.json"
cp -v "$OLD/appdata.wal" "$NEW/appdata.wal" 2>/dev/null || true
for b in "$OLD"/appdata.json.bak.*; do [ -f "$b" ] && cp -v "$b" "$NEW/"; done
```

Alternatively, set absolute paths when running:

```bash
DATA_FILE=/abs/path/appdata.json WAL_FILE=/abs/path/appdata.wal make run-todo
```
