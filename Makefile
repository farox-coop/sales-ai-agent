.PHONY: dev build down shell db-shell db-reset scrape-genia knowledge-reload
.PHONY: validate-env prod-build prod-up prod-down prod-restart prod-logs prod-status prod-setup prod-deploy
.PHONY: nginx-config nginx-config-http nginx-up nginx-down nginx-restart nginx-logs ssl-init

# --- Dev compose ---
COMPOSE_DEV := docker compose

# --- Prod compose aliases ---
COMPOSE_PROD := docker compose -f prod/docker-compose.yml
COMPOSE_NGINX := docker compose -f prod/nginx/docker-compose.nginx.yml

# =============================================================================
# Dev targets
# =============================================================================

dev:
	$(COMPOSE_DEV) up --build

build:
	$(COMPOSE_DEV) build

down:
	$(COMPOSE_DEV) down -v

shell:
	$(COMPOSE_DEV) exec app bash

db-shell:
	$(COMPOSE_DEV) exec postgres psql -U postgres -d lead_magnet

db-reset:
	$(COMPOSE_DEV) down -v
	$(COMPOSE_DEV) up --build

scrape-genia:
	@BUNDLE=$$(curl -sL https://genia.coop/ | grep -oP 'assets/index-[^"]+\.js' | head -1) && \
		echo "Downloading $$BUNDLE..." && \
		curl -sL "https://genia.coop/$$BUNDLE" > /tmp/genia_bundle.js
	python3 scripts/scrape_genia_to_md.py /tmp/genia_bundle.js

knowledge-reload:
	$(COMPOSE_DEV) exec app python3 -c "from src.knowledge.loader import knowledge_base; print(f'Loaded {knowledge_base.total_articles} articles, {knowledge_base.total_chars} chars')"

# =============================================================================
# Production targets
# =============================================================================

# --- Validation ---

validate-env:
	@test -f prod/.env || { echo "ERROR: prod/.env not found. Run: cp prod/.env.example prod/.env"; exit 1; }
	@grep -q 'POSTGRES_PASSWORD=postgres' prod/.env && echo "WARNING: POSTGRES_PASSWORD is still 'postgres' in prod/.env" || true
	@grep -q 'POSTGRES_PASSWORD=replace-with-strong-random-password' prod/.env && { echo "ERROR: POSTGRES_PASSWORD still has placeholder value in prod/.env"; exit 1; } || true
	@grep -q 'LLM_API_KEY=your-gateway-api-key' prod/.env && echo "WARNING: LLM_API_KEY still has placeholder value in prod/.env" || true

# --- App stack ---

prod-build: validate-env
	$(COMPOSE_PROD) pull app

prod-up: validate-env
	$(COMPOSE_PROD) up -d --wait

prod-down:
	$(COMPOSE_PROD) down

prod-restart:
	$(COMPOSE_PROD) restart

prod-logs:
	$(COMPOSE_PROD) logs -f --tail=100 $(SERVICE)

prod-status:
	@echo "=== Docker network ==="
	@docker network inspect sales-ai-network > /dev/null 2>&1 && echo "sales-ai-network: exists" || echo "sales-ai-network: MISSING"
	@echo ""
	@echo "=== App stack ==="
	@$(COMPOSE_PROD) ps
	@echo ""
	@echo "=== Nginx stack ==="
	@$(COMPOSE_NGINX) ps

# --- Full setup ---

prod-setup: validate-env
	@echo "=== Creating external network (if missing) ==="
	@docker network inspect sales-ai-network > /dev/null 2>&1 || docker network create sales-ai-network
	@echo "=== Pulling app image ==="
	$(COMPOSE_PROD) pull app
	@echo "=== Starting app stack ==="
	$(COMPOSE_PROD) up -d --wait
	@echo "=== Rendering HTTP-only nginx config ==="
	make nginx-config-http
	@echo "=== Starting nginx stack ==="
	$(COMPOSE_NGINX) up -d
	@echo ""
	@echo "prod-setup complete! App is running behind nginx (HTTP only)."
	@echo "Next: make ssl-init"

prod-deploy: validate-env
	@echo "=== Pulling latest code ==="
	git pull
	@echo "=== Pulling app image ==="
	$(COMPOSE_PROD) pull app
	@echo "=== Stopping nginx ==="
	$(COMPOSE_NGINX) down
	@echo "=== Cycling app ==="
	$(COMPOSE_PROD) down
	$(COMPOSE_PROD) up -d --wait
	@echo "=== Re-rendering nginx config ==="
	make nginx-config
	@echo "=== Starting nginx ==="
	$(COMPOSE_NGINX) up -d
	@echo ""
	@echo "Deploy complete!"

# --- Nginx config rendering ---

nginx-config: validate-env
	@echo "=== Rendering nginx configs ==="
	@. prod/.env && \
		for template in prod/nginx/conf.d/*.conf.template; do \
			conf=$$(echo $$template | sed 's/.template$$//'); \
			echo "  $$template -> $$conf"; \
			envsubst '$$DOMAIN' < $$template > $$conf; \
		done

nginx-config-http: validate-env
	@echo "=== Rendering HTTP-only nginx config ==="
	@rm -f prod/nginx/conf.d/ssl-app.conf
	@. prod/.env && \
		envsubst '$$DOMAIN' < prod/nginx/conf.d/default.conf.template > prod/nginx/conf.d/default.conf

# --- Nginx stack ---

nginx-up:
	$(COMPOSE_NGINX) up -d

nginx-down:
	$(COMPOSE_NGINX) down

nginx-restart:
	$(COMPOSE_NGINX) restart

nginx-logs:
	$(COMPOSE_NGINX) logs -f --tail=100 $(SERVICE)

# --- TLS bootstrap ---

ssl-init: validate-env
	@echo "=== Starting with HTTP-only nginx config ==="
	make nginx-config-http
	$(COMPOSE_NGINX) up -d
	@echo "=== Waiting for nginx to be ready ==="
	sleep 3
	@echo "=== Requesting Let's Encrypt certificate ==="
	@. prod/.env && \
		docker compose -f prod/nginx/docker-compose.nginx.yml run --rm \
			--entrypoint certbot \
			-e DOMAIN=$$DOMAIN \
			certbot \
			certonly --webroot \
				--webroot-path=/var/www/certbot \
				--email $$SSL_EMAIL \
				--agree-tos \
				--no-eff-email \
				-d $$DOMAIN
	@echo "=== Rendering full TLS nginx config ==="
	make nginx-config
	@echo "=== Reloading nginx with TLS config ==="
	$(COMPOSE_NGINX) restart
	@echo ""
	@echo "TLS bootstrap complete! Visit https://$$(grep DOMAIN prod/.env | cut -d= -f2)"
