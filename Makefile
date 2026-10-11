.PHONY: dev test lint e2e seed migrate build clean

dev:
	docker compose up --build

dev-local:
	@echo "Starting backend and frontend locally..."
	python -m uvicorn apps.api.main:app --reload --port 8000 &
	cd apps/web && npm run dev

test:
	pytest apps/api/tests -v
	cd apps/web && npm run test

lint:
	ruff check apps/api
	ruff format --check apps/api
	cd apps/web && npm run lint

e2e:
	cd apps/web && npx playwright test

seed:
	python scripts/seed_demo_data.py

demo: seed
	@echo "Demo seed complete. Persona: Elena Rostova (demo@jobpilot.ai / Password123!)"

migrate:
	alembic -c apps/api/alembic.ini upgrade head

build:
	docker compose build

clean:
	docker compose down -v
	rm -rf apps/web/dist apps/web/node_modules apps/api/__pycache__
