.PHONY: dev build down shell db-shell db-reset

dev:
	docker compose up --build

build:
	docker compose build

down:
	docker compose down -v

shell:
	docker compose exec app bash

db-shell:
	docker compose exec postgres psql -U postgres -d lead_magnet

db-reset:
	docker compose down -v
	docker compose up --build
