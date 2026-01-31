# ToDo & Notes Flask App

A simple single-user web app for managing to-dos and notes with JSON file persistence, rolling backups, and WAL-based recovery. Includes a minimal JSON API and a Bootstrap-based modern UI.

## Quickstart (Monorepo)

Requirements: Python 3.11+ recommended

From the monorepo root:

```bash
cd /Users/achaves/repos/personal/python-apps
scripts/dev.sh                # sets up .venv and installs apps in editable mode
make run-todo                 # run via console entry point (todo-app)
# or during development
make run-todo-dev             # run directly from source
```

The app runs on http://localhost:5000/ by default. Configure via environment variables:

- DATA_FILE (default: ./data/appdata.json)
- WAL_FILE (default: ./data/appdata.wal)
- BACKUP_COUNT (default: 10)
- PORT (default: 5000)
- DEBUG (default: 0; set DEBUG=1 to enable)

## Container image (GHCR)

Images are built and published by CI to GitHub Container Registry when tests pass on pushes to `main` or tags.

Pull and run (replace OWNER with your GitHub user/org name, lowercase):

```bash
docker pull ghcr.io/OWNER/todo:latest

docker run --rm -p 5000:5000 \
  -e PORT=5000 \
  -e DEBUG=0 \
  -v "$(pwd)/../../data:/app/data" \
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

## Architecture
- src/todo_app/__init__.py: Flask app factory; registers blueprints; health endpoint
- src/todo_app/config.py: configuration via env with defaults
- src/todo_app/storage.py: JsonStore handles
  - Validation of models
  - Atomic writes and backup rotation
  - WAL append and replay
  - CRUD for todos, notes, work items
- src/todo_app/api.py: JSON API endpoints
- src/todo_app/web.py: HTML routes and forms
- src/todo_app/templates/: Jinja templates using Bootstrap
- src/todo_app/static/: CSS
- src/todo_app/wsgi.py: WSGI module for gunicorn
- apps/todo/run.py: dev entrypoint to run from source
- apps/todo/tests/: pytest suite

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
