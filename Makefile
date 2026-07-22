.PHONY: dev build down shell db-shell db-reset scrape-genia knowledge-reload

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

scrape-genia:
	curl -sL https://genia.coop/assets/index-3OEbpqcP.js > /tmp/genia_bundle.js
	python3 scripts/scrape_genia_to_md.py /tmp/genia_bundle.js

knowledge-reload:
	docker compose exec app python3 -c "from src.knowledge.loader import knowledge_base; print(f'Loaded {knowledge_base.total_articles} articles, {knowledge_base.total_chars} chars')"
