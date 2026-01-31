.PHONY: help venv install install-all test run-todo run-todo-dev clean

PY?=python3
VENV=.venv
PIP=$(VENV)/bin/pip
PYTHON=$(VENV)/bin/python
PYTEST=$(VENV)/bin/pytest

help:
	@echo "Targets: venv, install, install-all, test, run-todo, run-todo-dev, clean"

venv:
	$(PY) -m venv $(VENV)
	$(PIP) install -U pip wheel

install: venv
	$(PIP) install -e apps/todo

install-all: venv
	@for app in apps/*; do \
	  if [ -f "$$app/pyproject.toml" ]; then \
	    echo "Installing $$app"; \
	    $(PIP) install -e "$$app"; \
	  fi; \
	done

test: install-all
	$(PYTEST) -q

run-todo: install
	$(VENV)/bin/todo-app

run-todo-dev:
	$(PYTHON) apps/todo/run.py

clean:
	rm -rf $(VENV) .pytest_cache **/__pycache__
