# Production Deployment Runbook — sales-ai-agent

## Architecture

Two independent Docker Compose stacks sharing an external network:

```
┌─────────────────────────────────────────────────────────────┐
│                      sales-ai-network                        │
│                                                              │
│  ┌──────────────────────┐   ┌─────────────────────────────┐ │
│  │  App Stack            │   │  Nginx/TLS Stack             │ │
│  │  prod/docker-compose  │   │  prod/nginx/docker-compose   │ │
│  │                       │   │                              │ │
│  │  app (Chainlit :8000) │◄──│  nginx (:80, :443)           │ │
│  │  postgres (:5432)     │   │  certbot (renew loop)         │ │
│  └──────────────────────┘   └─────────────────────────────┘ │
│                                                              │
│  Internet ───► nginx:443 ───► proxy_pass app:8000            │
└──────────────────────────────────────────────────────────────┘
```

- App code is **baked into the Docker image** (no bind mounts in prod)
- Nginx terminates TLS, proxies to app via Docker service name `app:8000`
- Certbot auto-renews via a 12h loop inside its container
- Nginx auto-reloads via a 6h loop to pick up renewed certificates

## Prerequisites

- **VPS**: Debian 12 or Ubuntu 24.04 LTS (1 vCPU, 1 GB RAM minimum)
- **Domain**: `chat.genia.coop` (DNS A record pointing to the VPS public IP)
- **Ports**: 22 (SSH), 80 (HTTP), 443 (HTTPS) open

## Deployment Steps

### 1. Bootstrap the server (first time only)

```bash
ssh root@<vps-ip>
apt-get update && apt-get install -y git
git clone <repo-url> /opt/sales-ai-agent
cd /opt/sales-ai-agent
bash prod/setup-server.sh
```

This installs Docker, UFW, and creates the shared `sales-ai-network`.

### 2. Configure environment

```bash
cp prod/.env.example prod/.env
```

Edit `prod/.env` with real values:
- `DOMAIN=chat.genia.coop`
- `SSL_EMAIL=admin@genia.coop`
- `POSTGRES_PASSWORD` — generate a strong password: `openssl rand -hex 32`
- `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` — your LLM gateway credentials
- Update `SQLALCHEMY_ASYNC_URL` and `DATABASE_SYNC_URL` with the real password

### 3. Initial deploy (HTTP-only)

```bash
make prod-setup
```

This will:
1. Build the app Docker image
2. Start app + postgres
3. Render HTTP-only nginx config (ACME challenge path + redirect)
4. Start nginx + certbot

At this point, visiting `http://chat.genia.coop` should redirect to HTTPS (which won't work yet — we need the cert).

### 4. Issue TLS certificate

```bash
make ssl-init
```

This runs certbot with the webroot plugin to obtain a Let's Encrypt certificate, then renders the full TLS nginx config and reloads.

After this, `https://chat.genia.coop` should load the Chainlit chat.

### 5. Verify

```bash
make prod-status
```

All services should be `Up` and `healthy`.

## Day-to-Day Operations

### Check status

```bash
make prod-status
```

### View logs

```bash
make prod-logs           # App + postgres
make nginx-logs          # Nginx + certbot
```

Add `SERVICE=app` to filter: `make prod-logs SERVICE=app`

### Deploy updates

```bash
git pull
make prod-deploy
```

This rebuilds the image, cycles the app container (with zero-downtime for postgres), and reloads nginx.

### Restart services

```bash
make prod-restart        # App + postgres
make nginx-restart       # Nginx + certbot
```

### Stop everything

```bash
make prod-down
make nginx-down
```

## TLS Certificate Renewal

Certbot runs `certbot renew` every 12 hours inside its container. Nginx reloads its config every 6 hours to pick up renewed certificates. No manual intervention needed.

To force a renewal test:

```bash
docker compose -f prod/nginx/docker-compose.nginx.yml exec certbot certbot renew --dry-run
```

## Environment Variables

All production config lives in `prod/.env`. The template at `prod/.env.example` documents every variable.

| Variable | Description |
|---|---|
| `DOMAIN` | Public domain name |
| `SSL_EMAIL` | Let's Encrypt notification email |
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `LLM_API_KEY` | LLM gateway API key |
| `LLM_BASE_URL` | LLM gateway base URL |
| `LLM_MODEL` | Model name to request |
| `SQLALCHEMY_ASYNC_URL` | Async DB connection string |
| `DATABASE_SYNC_URL` | Sync DB connection string |

## Troubleshooting

### "network sales-ai-network not found"
Run: `docker network create sales-ai-network`

### "certbot: command not found" or cert issues
Make sure `prod/.env` has the correct `DOMAIN` and the DNS A record is pointing to the server. Check certbot logs:
```bash
make nginx-logs SERVICE=certbot
```

### App not connecting to postgres
Verify `POSTGRES_PASSWORD` in `prod/.env` matches what's in `SQLALCHEMY_ASYNC_URL` and `DATABASE_SYNC_URL`.

### WebSocket / real-time chat not working
Check that nginx config includes the WebSocket upgrade headers. Run `make nginx-config` to re-render templates and `make nginx-restart` to apply.

### "port already in use" on 80/443
Something else is listening. Check with `ss -tlnp | grep -E ':80|:443'`.
