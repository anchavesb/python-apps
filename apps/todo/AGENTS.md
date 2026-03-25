# AGENTS.md - todo (Legacy App)

A traditional multiuser ToDo application.

## Project Overview
- **Role:** Web app for multiple users to track tasks/notes.
- **Tech Stack:** Flask, SQLAlchemy (PostgreSQL), Authlib.
- **Architecture:** Classic MVC (Models, Routes, Views).

## Build and Setup
- **Install (from the root):** `make install-todo`.
- **Run (dev):** `python apps/todo/run.py` or `todo-app`.
- **Database:** PostgreSQL required for production.

## Core Modules
- `todo_app/__main__.py`: Main Flask initialization.
- `models/`: SQLAlchemy database schema.
- `routes/`: Flask blueprint routes.

## Testing Instructions
- **Run app tests:** `pytest apps/todo/` (repo root).

## Style Guidelines
- **Flask Patterns:** Use standard Flask application factory.
- **Auth:** Uses OAuth and JWT through Authlib.
- Does NOT depend on `dolores-common` (standalone legacy).

## Quality Gates
Every code change must pass before merging:
- **Lint:** `make lint` (`ruff check .` — zero errors required)
- **Tests:** `make test` (all tests must pass)

## Security Considerations
- **CSRF Protection:** Check Flask-WTF config.
- **Migrations:** Managed via `Alembic` or `Flask-Migrate`.
