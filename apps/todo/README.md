# ToDo & Notes Flask App

A simple single-user web app for managing to-dos and notes with JSON file persistence, rolling backups, and WAL-based recovery. Includes a minimal JSON API and a Bootstrap-based modern UI.

## Features
- To-Dos
  - Fields: id (UUID), title (required), description (optional), tags (dict; requires category and priority), done (bool), due_date, created_at, updated_at
  - CRUD + mark done
- Notes
  - Fields: id (UUID), title (required), note (optional), tags (dict; requires category and priority), created_at, updated_at
  - CRUD
- Tags are string→string, required keys: category, priority
- Priorities: low, medium, high, urgent
- Persistence: JSON file with atomic writes and rotating backups
- Recovery: Append-only WAL (write-ahead log) replay; auto-recovery on startup
- Minimal JSON API
- Modern UI with Bootstrap 5
- Unit tests (pytest)

## Quickstart

Requirements: Python 3.11+ recommended

```bash
./scripts/setup.sh
source .venv/bin/activate
python run.py
```

The app runs on http://localhost:5000/ by default. Configure via environment variables:

- DATA_FILE (default: ./data/appdata.json)
- WAL_FILE (default: ./data/appdata.wal)
- BACKUP_COUNT (default: 10)
- PORT (default: 5000)
- DEBUG (default: 1)

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

## Web UI
- Index shows lists of to-dos and notes
- Filter by text, category, priority, and status (for todos)
- Create/edit forms enforce category and priority and allow additional key=value tags

## Architecture
- app/__init__.py: Flask app factory; registers blueprints; health endpoint
- app/config.py: configuration via env with defaults
- app/storage.py: JsonStore handles
  - Validation of models
  - Atomic writes and backup rotation
  - WAL append and replay
  - CRUD for todos and notes
- app/api.py: JSON API endpoints
- app/web.py: HTML routes and forms
- app/templates/: Jinja templates using Bootstrap
- app/static/: CSS
- run.py: entrypoint to run the app
- tests/: pytest suite

### Persistence Details
- Main data file: DATA_FILE
- Backups: DATA_FILE.bak.1 .. .bak.N (N=BACKUP_COUNT)
- WAL: line-delimited JSON entries of operations. On startup, if the main file is invalid, the app restores from latest valid backup and replays WAL; if no backup exists, it replays WAL onto an empty state.

## Testing

```bash
source .venv/bin/activate
pytest -q
```

## Optional: Docker
A Dockerfile can be added on request to run the app in a container.

## Notes
- Single-user; no authentication enabled. Consider adding HTTP Basic Auth behind a reverse proxy if needed.
- Dates
  - due_date accepts YYYY-MM-DD or ISO string; stored as string
  - created_at/updated_at stored as UTC ISO (YYYY-MM-DDTHH:MM:SSZ)
