SHELL := /bin/bash
.PHONY: help run-backend run-worker run-frontend db-migrate db-revise temporal-up temporal-down

help:
	@echo "Available targets:"
	@echo "  run-backend     - Launch FastAPI dev server (uvicorn) from backend/"
	@echo "  run-worker      - Launch Temporal worker process from backend/"
	@echo "  run-frontend    - Launch Vite dev server from frontend/"
	@echo "  db-migrate      - Apply database migrations (Alembic)"
	@echo "  db-revise       - Create new Alembic revision (NAME=message)"
	@echo "  temporal-up     - Start Temporal + Postgres stack via docker-compose"
	@echo "  temporal-down   - Stop Temporal + Postgres stack"

run-backend:
	cd backend && uvicorn app.main:app --reload

run-worker:
	cd backend && python -m app.temporal.worker

run-frontend:
	cd frontend && npm run dev

db-migrate:
	cd backend && alembic upgrade head

db-revise:
	cd backend && alembic revision --autogenerate -m "$${NAME:-auto}"

temporal-up:
	cd infra && docker compose up -d temporal temporal-ui postgres

temporal-down:
	cd infra && docker compose down
