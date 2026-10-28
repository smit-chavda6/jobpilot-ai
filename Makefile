# JobPilot AI developer commands. Windows without make: run the commands shown in README.md.
API := apps/api
WEB := apps/web
PY  := $(if $(wildcard $(API)/.venv/Scripts/python.exe),$(API)/.venv/Scripts/python.exe,$(API)/.venv/bin/python)

.PHONY: help setup dev up down logs api web test test-api test-web test-pg lint typecheck e2e e2e-stack seed seed-stack migrate eval openapi

help:
	@echo "setup      create .env, Python venv and node_modules"
	@echo "dev        full stack in Docker (http://localhost:8080)"
	@echo "api / web  run API (:8000) or Vite dev server (:5173) locally"
	@echo "test       backend + frontend unit/integration tests"
	@echo "test-pg    backend tests against a throwaway Postgres container"
	@echo "lint       ruff + tsc;  typecheck: mypy + tsc"
	@echo "e2e        Playwright journey (starts its own API + web)"
	@echo "seed       DEMO data into the local DB;  seed-stack: into the Docker stack"
	@echo "migrate    alembic upgrade head (local DB)"
	@echo "eval       matching evaluation harness"

setup:
	test -f .env || cp .env.example .env
	cd $(API) && python -m venv .venv
	$(PY) -m pip install -e "$(API)[dev]"
	cd $(WEB) && npm ci

dev up:
	docker compose up --build -d
	@echo "JobPilot is starting at http://localhost:$${WEB_PORT:-8080}"

down:
	docker compose down

logs:
	docker compose logs -f api worker

api: migrate
	cd $(API) && ../../$(PY) -m uvicorn app.main:app --reload --port 8000

web:
	cd $(WEB) && npm run dev

migrate:
	cd $(API) && mkdir -p var && ../../$(PY) -m alembic upgrade head

test: test-api test-web

test-api:
	cd $(API) && ../../$(PY) -m pytest -q --cov=app --cov-report=term-missing:skip-covered

test-web:
	cd $(WEB) && npm test

test-pg:
	docker run -d --rm --name jp-test-pg -e POSTGRES_PASSWORD=test -e POSTGRES_DB=jp_test -p 55432:5432 postgres:16-alpine
	until docker exec jp-test-pg pg_isready -U postgres -d jp_test >/dev/null 2>&1; do sleep 1; done
	cd $(API) && TEST_DATABASE_URL=postgresql+asyncpg://postgres:test@127.0.0.1:55432/jp_test ../../$(PY) -m pytest -q --ignore=tests/test_migrations.py; \
	  status=$$?; docker stop jp-test-pg >/dev/null; exit $$status

lint:
	cd $(API) && ../../$(PY) -m ruff check app tests alembic scripts && ../../$(PY) -m ruff format --check app tests alembic scripts
	cd $(WEB) && npm run lint

typecheck:
	cd $(API) && ../../$(PY) -m mypy app
	cd $(WEB) && npm run typecheck

e2e:
	cd $(WEB) && npx playwright test

e2e-stack:
	cd $(WEB) && E2E_BASE_URL=http://localhost:$${WEB_PORT:-8080} npx playwright test

seed: migrate
	cd $(API) && ../../$(PY) -m scripts.seed_demo

seed-stack:
	docker compose exec api python -m scripts.seed_demo

eval:
	cd $(API) && ../../$(PY) ../../evals/matching/runner.py

openapi:
	cd $(API) && ../../$(PY) -c "import json; from app.main import app; open('../../packages/contracts/openapi.json','w').write(json.dumps(app.openapi(), indent=2))"
	cd $(WEB) && npm run gen:api
