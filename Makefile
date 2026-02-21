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
	@for lib in libs/*; do \
	  if [ -f "$$lib/pyproject.toml" ]; then \
	    echo "Installing $$lib"; \
	    $(PIP) install -e "$$lib"; \
	  fi; \
	done
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

# Docker local build/push (GHCR)
APP?=todo
TAG?=dev
GHCR_OWNER?=$(shell git config --get remote.origin.url | sed -E 's|.*[:/](.+)/[^/]+(\.git)?|\1|' | tr '[:upper:]' '[:lower:]')
IMAGE=ghcr.io/$(GHCR_OWNER)/$(APP):$(TAG)

.PHONY: docker-info docker-build docker-push docker-build-all docker-push-all

docker-info:
	@echo "APP=$(APP)" && echo "TAG=$(TAG)" && echo "GHCR_OWNER=$(GHCR_OWNER)" && echo "IMAGE=$(IMAGE)"

docker-build:
	@if echo "$(APP)" | grep -q '^dolores-'; then \
	  docker build -t $(IMAGE) -f apps/$(APP)/Dockerfile .; \
	else \
	  docker build -t $(IMAGE) apps/$(APP); \
	fi

docker-push:
	docker push $(IMAGE)

docker-build-all:
	@for app in apps/*; do \
	  if [ -f "$$app/Dockerfile" ]; then \
	    name=$$(basename "$$app"); \
	    echo "Building $$name"; \
	    if echo "$$name" | grep -q '^dolores-'; then \
	      docker build -t ghcr.io/$(GHCR_OWNER)/$$name:$(TAG) -f "$$app/Dockerfile" .; \
	    else \
	      docker build -t ghcr.io/$(GHCR_OWNER)/$$name:$(TAG) "$$app"; \
	    fi; \
	  fi; \
	done

docker-push-all:
	@for app in apps/*; do \
	  if [ -f "$$app/Dockerfile" ]; then \
	    name=$$(basename "$$app"); \
	    echo "Pushing $$name"; \
	    docker push ghcr.io/$(GHCR_OWNER)/$$name:$(TAG); \
	  fi; \
	done
