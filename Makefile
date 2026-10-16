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
	uv run python -m scripts.check_stack
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
	uv run mypy --strict packages apps/api services/demo-services/src chaos
	cd apps/web && npm run lint && npm run typecheck
build-web:
	cd apps/web && npm run build
smoke:
	uv run pytest -m docker -v
chaos-kill:
	uv run python -m chaos.scenarios.scn_001_service_kill
chaos-lag:
	uv run python -m chaos.scenarios.scn_002_replica_lag
investigate:
	@test -n "$(ID)" || (echo "Usage: make investigate ID=<incident_id>"; exit 2)
	uv run python -m scripts.investigate "$(ID)"
eval:
	uv run python -m aipi_evaluation.cli $(EVAL_ARGS)
record-golden:
	uv run python -m aipi_evaluation.record --repeats $(or $(REPEATS),3)
demo: up
	$(MAKE) seed-traffic
	uv run python -m scripts.demo
	$(MAKE) eval
