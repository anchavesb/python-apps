# python-apps Monorepo

[![CI](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/REPO/actions/workflows/ci.yml)
[![GHCR - todo](https://img.shields.io/badge/GHCR-todo-blue?logo=github)](https://ghcr.io/OWNER/todo)


A lightweight Python monorepo for applications and (future) shared libraries.

Structure:
- apps/ — individual applications (each has its own pyproject.toml)
- libs/ — shared libraries (future)
- conftest.py — adds apps/*/src to sys.path for testing
- Makefile — common tasks (venv, install, test, run)
- scripts/dev.sh — bootstrap a dev environment

## Development Quickstart

From repo root:

```bash
make install-all    # create venv and install apps in editable mode
make test           # run test suite for all apps
make run-todo       # run via console script (todo-app)
make run-todo-dev   # run directly from source
```

Or use the helper script:

```bash
scripts/dev.sh
source .venv/bin/activate
pytest -q
```

## CI and container publishing (GHCR)

This repo includes a GitHub Actions workflow at `.github/workflows/ci.yml` that:
- test: installs all apps in editable mode and runs pytest across the monorepo on PRs and pushes
- discover: finds apps under `apps/*` that contain a `pyproject.toml` and builds a job matrix
- build-and-push: builds and pushes images to GitHub Container Registry (GHCR) for each app — only on push events (main branch or tags) and only if tests pass

Image naming:
- `ghcr.io/<OWNER>/<app>` (OWNER is your GitHub user/organization; app is the directory name under `apps/`)
- Tags:
  - `latest` on pushes to `main`
  - `sha-<shortsha>` on any push
  - `<git tag>` when pushing tags like `v1.2.3`

Permissions and visibility:
- The workflow logs into `ghcr.io` using `${{ secrets.GITHUB_TOKEN }}` with `packages: write`
- Public repos: images are free to publish
- Private repos: make sure GHCR package visibility is set as you prefer; pulling may require authentication

Pulling and running images:
```bash
# replace OWNER with your GitHub username/org (lowercase)
# example app: todo

# Pull
docker pull ghcr.io/OWNER/todo:latest

# Run
docker run --rm -p 5000:5000 \
  -e PORT=5000 \
  -e DEBUG=0 \
  -v "$(pwd)/data:/app/data" \
  ghcr.io/OWNER/todo:latest
```

## Monorepo: How to add a new app (with Docker)

To create a new app in `/Users/achaves/repos/personal/python-apps`:

1. Create skeleton and metadata:
   ```bash
   cd /Users/achaves/repos/personal/python-apps
   mkdir -p apps/myapp/src/myapp apps/myapp/tests
   cp apps/todo/pyproject.toml apps/myapp/pyproject.toml
   # edit apps/myapp/pyproject.toml:
   #   [project] name = "myapp"
   #   [project.scripts] "myapp" = "myapp.__main__:main"
   ```
2. Add code and entry point:
   ```bash
   printf '%s\n' "def main():\n    print('hello from myapp')" > apps/myapp/src/myapp/__main__.py
   printf '%s\n' "__all__ = []" > apps/myapp/src/myapp/__init__.py
   ```
3. Add Dockerfile and WSGI entrypoint (for gunicorn):
   - `apps/myapp/Dockerfile`
     ```dockerfile
     # syntax=docker/dockerfile:1
     FROM python:3.12-slim

     ENV PYTHONDONTWRITEBYTECODE=1 \
         PYTHONUNBUFFERED=1 \
         PIP_NO_CACHE_DIR=1

     RUN useradd -m appuser
     WORKDIR /app

     COPY pyproject.toml ./
     COPY src ./src

     RUN python -m pip install --upgrade pip wheel \
         && python -m pip install gunicorn \
         && python -m pip install -e .

     ENV PORT=5000
     EXPOSE 5000
     RUN mkdir -p /app/data && chown -R appuser:appuser /app
     USER appuser

     CMD ["sh", "-c", "exec gunicorn -w ${GUNICORN_WORKERS:-2} -b 0.0.0.0:${PORT:-5000} myapp.wsgi:app"]
     ```
   - `apps/myapp/src/myapp/wsgi.py`
     ```python
     from . import create_app
     app = create_app()
     ```
4. Install and test locally:
   ```bash
   make install-all
   make test
   myapp               # runs the console script, if defined
   ```
5. CI/CD:
   - On PRs: tests will run
   - On pushes to main (or tags): tests run, then images are built and pushed to GHCR
   - Images published as: `ghcr.io/OWNER/myapp:latest` (main), plus `sha-*` and tag versions

## Local Docker build (optional)
```bash
# build from an app directory
cd apps/todo
docker build -t ghcr.io/OWNER/todo:dev .

docker run --rm -p 5000:5000 \
  -v "$(pwd)/../../data:/app/data" \
  ghcr.io/OWNER/todo:dev
```
