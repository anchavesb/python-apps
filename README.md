# python-apps Monorepo

A lightweight Python monorepo for applications and (future) shared libraries.

Structure:
- apps/ — individual applications (each has its own pyproject.toml)
- libs/ — shared libraries (future)
- conftest.py — adds apps/*/src to sys.path for testing
- Makefile — common tasks (venv, install, test, run)
- scripts/dev.sh — bootstrap a dev environment

## First app: ToDo

Simple Flask app for todos, notes, and work items.

Commands:

```bash
# From repo root
make install-all    # create venv and install apps in editable mode
make test           # run test suite
make run-todo       # run via console script (todo-app)
make run-todo-dev   # run directly from source
```

Or use the helper script:

```bash
scripts/dev.sh
source .venv/bin/activate
pytest -q
```
