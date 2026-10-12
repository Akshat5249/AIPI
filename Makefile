SHELL := /bin/bash
UV_CACHE_DIR ?= /tmp/aipi-uv-cache
export UV_CACHE_DIR
COMPOSE = docker compose --env-file .env -f infra/docker/compose.yml
.PHONY: setup setup-env up down seed-traffic test lint build-web smoke chaos-kill chaos-lag investigate eval record-golden demo
setup-env:
	python3.12 scripts/init_env.py
setup: setup-env
	uv sync --all-packages --frozen
	cd apps/web && npm ci --cache /tmp/aipi-npm-cache
up: setup-env
	$(COMPOSE) up -d --build --wait --wait-timeout 180
	uv run python scripts/check_stack.py
down:
	$(COMPOSE) --profile traffic down
seed-traffic:
	$(COMPOSE) --profile traffic up -d --wait traffic
test:
	uv run pytest
	cd apps/web && npm test
lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy --strict packages apps/api services/demo-services/src
	cd apps/web && npm run lint && npm run typecheck
build-web:
	cd apps/web && npm run build
smoke:
	uv run pytest -m docker -v
chaos-kill chaos-lag investigate eval record-golden demo:
	@echo "$@ is scheduled for its later phase; see PROGRESS.md"; exit 2
