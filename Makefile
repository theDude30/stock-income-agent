.PHONY: up down logs build test test-backend test-frontend lint migrate shell-api shell-db

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

test: test-backend test-frontend

test-backend:
	docker compose run --rm api pytest

test-frontend:
	docker compose run --rm web npm test -- --run

lint:
	docker compose run --rm api ruff check .
	docker compose run --rm web npm run lint

migrate:
	docker compose run --rm api alembic upgrade head

shell-api:
	docker compose exec api bash

shell-db:
	docker compose exec db psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}
