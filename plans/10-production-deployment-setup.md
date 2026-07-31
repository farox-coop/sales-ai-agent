# Production Deployment Setup for sales-ai-agent

## Context

The sales-ai-agent project currently has only a dev setup (Dockerfile, docker-compose.yml, Makefile all dev-focused with bind mounts, `--watch` mode, and `postgres/postgres` credentials). We need to add a production deployment setup for a VPS, following the same proven pattern from the genia-desarrollo-de-producto project: two decoupled Docker Compose stacks (app + nginx/certbot) bridged by an external Docker network, with nginx reverse-proxying to the Chainlit app and certbot handling TLS via webroot ACME challenges.

The user wants to keep building Docker images locally (not pushing to a registry yet), so the prod compose will use `build: .` rather than a pre-built image reference.

**All production files go inside `prod/`** — clean separation from dev config at the repo root.

## Directory Layout

```
prod/
├── .env.example                  # Template for per-deployment production config
├── docker-compose.yml            # App stack (app + postgres)
├── setup-server.sh               # One-time host bootstrap script
├── DEPLOYMENT.md                 # Human runbook
└── nginx/
    ├── nginx.conf                # Main nginx config
    ├── conf.d/
    │   ├── default.conf.template # HTTP → HTTPS redirect (port 80)
    │   └── ssl-app.conf.template # TLS-terminated proxy to app (port 443)
    └── docker-compose.nginx.yml  # Nginx + certbot stack
```

Files at repo root that remain shared:
- `Dockerfile` — serves both dev and prod (compose overrides handle the differences)
- `docker-compose.yml` — dev only (bind mounts, --watch, postgres/postgres)
- `Makefile` — dev + prod targets

## Reference Pattern (from genia-desarrollo-de-producto)

The genia project uses this architecture:

1. **Two independent compose projects** sharing `sales-ai-network` (external Docker network)
2. **App stack** (`prod/docker-compose.yml`): app + postgres
3. **Nginx/TLS stack** (`prod/nginx/docker-compose.nginx.yml`): nginx + certbot, sharing `certbot-www` and `certbot-conf` volumes
4. **envsubst-templated nginx configs**: `.conf.template` files rendered at deploy time
5. **HTTP-first TLS bootstrap**: `make ssl-init` starts with HTTP-only nginx, issues cert, then switches to full TLS config
6. **Makefile-driven orchestration**: `prod-setup`, `prod-deploy`, `ssl-init`, `validate-env`, etc.

The core innovations we'll replicate:

- Two decoupled stacks → independent lifecycle (update app without touching nginx)
- External network → service-name DNS resolution between stacks
- Template rendering via `envsubst` → domain/cert names injected from `.env`
- HTTP→TLS bootstrap → nginx can start before certs exist
- Certbot renew loop container → no cron, no external scripts
- One-time `prod/setup-server.sh` → Docker + deps + UFW on fresh Debian/Ubuntu

## Files to Create (all under `prod/`)

### 1. `prod/.env.example`

Template for per-deployment production config. Variables needed:

- `DOMAIN` — `chat.genia.coop`
- `SSL_EMAIL` — email for Let's Encrypt notifications
- `POSTGRES_PASSWORD` — strong random password (not `postgres`)
- `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_MAX_TOKENS`, `LLM_TEMPERATURE`
- `SQLALCHEMY_ASYNC_URL`, `DATABASE_SYNC_URL` — using `postgres` hostname, real password

### 2. `prod/docker-compose.yml`

App stack for production:

- **app**: `build: .` (context at repo root), no bind mounts (code is baked into image), no `--watch`, `restart: always`, on external network `sales-ai-network`, depends_on postgres (healthy), env_file `prod/.env`, command `chainlit run src/main.py --host 0.0.0.0 --port 8000` (no --watch). Healthcheck: `curl -f http://localhost:8000/healthz` or similar.
- **postgres**: `postgres:16-alpine`, real password from env, `restart: always`, named volume `pgdata`, healthcheck as in dev, on `sales-ai-network`
- Network: `sales-ai-network` (external: true)
- No published ports on app (all traffic via nginx)

### 3. `prod/nginx/nginx.conf`

Main nginx config, identical pattern to genia:

- Standard `http {}` block
- WebSocket upgrade map (`$connection_upgrade`)
- `include /etc/nginx/conf.d/*.conf;`

### 4. `prod/nginx/conf.d/default.conf.template`

HTTP (port 80) server block:

- ACME challenge: `location /.well-known/acme-challenge/ { root /var/www/certbot; }`
- Everything else: `return 301 https://$host$request_uri;`

### 5. `prod/nginx/conf.d/ssl-app.conf.template`

HTTPS (443) server block:

- `server_name ${DOMAIN};`
- `ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;`
- `ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;`
- TLSv1.2/TLSv1.3, http2, client_max_body_size 50m
- `proxy_pass http://app:8000;` (Chainlit serves on 8000, reached via shared network)
- WebSocket upgrade headers (Chainlit needs WebSocket for real-time chat)
- Standard proxy headers (`X-Forwarded-For`, `X-Forwarded-Proto`, `Host`)

### 6. `prod/nginx/docker-compose.nginx.yml`

Nginx + certbot stack:

- **nginx**: `nginx:1.27-alpine`, publishes 80 and 443, mounts `prod/nginx/nginx.conf` + `prod/nginx/conf.d/` + certbot volumes, background reload loop (6h), `restart: unless-stopped`, on `sales-ai-network`
- **certbot**: `certbot/certbot:v2.11.0`, mounts same two volumes, renew loop (12h), `restart: unless-stopped`, on `sales-ai-network`
- Volumes: `certbot-www`, `certbot-conf`
- Network: `sales-ai-network` (external: true)

### 7. `prod/setup-server.sh`

One-time host bootstrap (adapted from genia):

- Install: make, gettext-base (envsubst), git, openssl, ca-certificates, curl, gnupg
- Install Docker if missing (via get.docker.com)
- Verify compose plugin
- Add deploy user to docker group
- Configure UFW: default deny incoming, allow outgoing, limit ssh, allow http/https
- Print next steps

### 8. `prod/DEPLOYMENT.md`

Human runbook covering: prerequisites, DNS setup, server bootstrap, clone + `prod/.env`, `make prod-setup`, `make ssl-init`, `make prod-status`, updates via `make prod-deploy`.

## Files to Modify (at repo root)

### 9. `Makefile`

Add production targets alongside existing dev targets. New compose aliases:

```makefile
COMPOSE_PROD := docker compose -f prod/docker-compose.yml
COMPOSE_NGINX := docker compose -f prod/nginx/docker-compose.nginx.yml
```

New targets (following genia naming):

- `validate-env` — fail if `prod/.env` missing or critical vars still at defaults (e.g. `POSTGRES_PASSWORD=postgres`)
- `prod-pull`, `prod-up`, `prod-down`, `prod-restart`, `prod-logs`
- `prod-status` — check network exists, ps on both stacks
- `prod-setup` — create network → prod-up → nginx-config-http → nginx-up
- `prod-deploy` — git pull → prod-build → nginx-down → prod-down → prod-up → nginx-up
- `nginx-config` — envsubst all `.template` → `.conf` inside `prod/nginx/conf.d/`
- `nginx-config-http` — envsubst only default.conf, delete ssl configs inside `prod/nginx/conf.d/`
- `nginx-up`, `nginx-down`, `nginx-restart`, `nginx-logs`
- `ssl-init` — full TLS bootstrap: HTTP config → nginx up → certbot certonly → full config → nginx restart

### 10. `.gitignore`

Add entries for:

- Generated nginx config files: `prod/nginx/conf.d/*.conf` (but keep `.conf.template`)
- `prod/.env`
- `.env` (confirm already present)

### 11. `Dockerfile` (optional for this phase)

The current Dockerfile works for prod since it copies `src/` and `data/` and has a reasonable CMD. The compose override will remove `--watch`. The user wants to keep the current build approach.

Since `prod/docker-compose.yml` is one level deep, the build context must be the repo root:
```yaml
services:
  app:
    build:
      context: ..
      dockerfile: Dockerfile
```

## Verification

1. On a test VPS (or local simulation):
   - Run `bash prod/setup-server.sh` — verify Docker + deps installed
   - Clone repo, `cp prod/.env.example prod/.env`, edit with real values
   - `make prod-setup` — verify network created, app + postgres + nginx (HTTP only) running
   - Browse to domain on HTTP — verify ACME challenge path works, other paths redirect to HTTPS
   - `make ssl-init` — verify cert issued, nginx restarted with HTTPS
   - Browse to `https://<domain>` — verify Chainlit chat loads with TLS
   - `make prod-status` — verify all services healthy
   - `make prod-deploy` — verify update flow works

2. Simulate cert renewal: check certbot container logs for successful `certbot renew` dry runs

## Resolved Decisions

- **Domain**: `chat.genia.coop`
- **Dockerfile**: Keep running as root (same as genia reference), defer non-root user to follow-up
- **Production directory**: All prod files under `prod/` — one folder to rule them all
