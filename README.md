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

# Monorepo: How to add a new app

To create a new app in the monorepo at `/Users/achaves/repos/personal/python-apps`:

1. Create a new skeleton:
   ```bash
   cd /Users/achaves/repos/personal/python-apps
   mkdir -p apps/myapp/src/myapp apps/myapp/tests
   cp apps/todo/pyproject.toml apps/myapp/pyproject.toml
   # edit apps/myapp/pyproject.toml: set project.name to "myapp" and script to myapp.__main__:main
   ```
2. Add code and entry point:
   ```bash
   printf '%s\n' "def main():\n    print('hello from myapp')" > apps/myapp/src/myapp/__main__.py
   printf '%s\n' "__all__ = []" > apps/myapp/src/myapp/__init__.py
   ```
3. Install and run:
   ```bash
   make install-all
   myapp
   ```
4. Add tests in `apps/myapp/tests` and run `make test`.
