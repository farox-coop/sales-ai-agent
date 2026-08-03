# 13 — GitHub Actions + GHCR Deploy

## Situación actual
- No hay GitHub workflows en este repo
- `prod/docker-compose.yml` usa `build:` local (la imagen se construye en el VPS)
- `Makefile` hace `docker compose build` en cada deploy

## Objetivo
Cada push a `main` buildea la imagen en GitHub Actions y la publica en `ghcr.io/farox-coop/sales-ai-agent-app`. El VPS solo hace `docker compose pull`.

---

## Cambios

### 1. Crear `.dockerignore`

```
.git
__pycache__
*.pyc
.env
prod/.env
plans/
```

### 2. Crear `.github/workflows/_build-and-publish-images.yml`

Workflow reusable:
- `workflow_call`
- `permissions: contents: read, packages: write`
- Steps:
  1. `actions/checkout@v4`
  2. Normalizar owner a lowercase (`GITHUB_REPOSITORY_OWNER,,`)
  3. `docker/setup-buildx-action@v3`
  4. `docker/login-action@v3` → `ghcr.io`, `GITHUB_TOKEN`
  5. `docker/metadata-action@v5` → imagen `ghcr.io/<lowercase-owner>/sales-ai-agent-app`, tags `latest` / `sha-<hash>` / branch
  6. `docker/build-push-action@v6` → context `.`, Dockerfile raíz, push `true`, cache `type=gha,scope=app`

Sin build-args ni secrets como build-args (todas las vars de este proyecto son runtime).

### 3. Crear `.github/workflows/build-and-publish.yml`

- `on: push: branches: [main], workflow_dispatch:`
- `permissions: contents: read, packages: write`
- `concurrency: group: build-publish-${{ github.workflow }}-${{ github.ref }}, cancel-in-progress: true`
- Jobs: `build-and-publish` → `uses: ./.github/workflows/_build-and-publish-images.yml`, `secrets: inherit`

### 4. Modificar `prod/docker-compose.yml`

Servicio `app`:
- **Quitar** bloque `build:`
- **Cambiar** `image: sales-ai-agent:latest` → `image: ${APP_IMAGE:?Set APP_IMAGE in .env}:${IMAGE_TAG:-latest}`

### 5. Actualizar `prod/.env.example`

Agregar:
```env
# --- GHCR image (required on the server) ---
APP_IMAGE=ghcr.io/farox-coop/sales-ai-agent-app
IMAGE_TAG=latest
```

### 6. Actualizar `Makefile`

| Target | Antes | Después |
|--------|-------|---------|
| `prod-build` | `$(COMPOSE_PROD) build` | `$(COMPOSE_PROD) pull app` |
| `prod-setup` | `up -d --build --wait` | `pull app` + `up -d --wait` |
| `prod-deploy` | `git pull` + `build` + cycle | `git pull` + `pull app` + cycle |

Sin `prod-build-local` (solo GHCR, sin build local en prod).

### 7. Actualizar `prod/setup-server.sh`

Agregar a instrucciones finales:
```bash
echo "  2.5. Login a GHCR para poder hacer pull:"
echo "     echo \$GHCR_TOKEN | docker login ghcr.io -u TU_USUARIO_GITHUB --password-stdin"
```

### 8. Actualizar `prod/DEPLOYMENT.md`

- Nueva sección "GHCR Authentication" explicando login al registry
- Actualizar pasos de deploy: imagen se baja de GHCR, no se buildea en el VPS
- Mencionar workflow `build-and-publish.yml` que corre en GitHub Actions

---

## Lo que NO cambia

- Dockerfile
- Nginx configs y stack de TLS
- Dev targets del Makefile
- `docker-compose.yml` de dev (raíz)
- Arquitectura de red (dos stacks en `sales-ai-network`)

---

## Workflows resultantes

```
.github/workflows/
├── build-and-publish.yml          # push a main → build + push a GHCR
└── _build-and-publish-images.yml  # reusable: login, build, push
```

---

## Flujo de deploy final

```
push a main
  └── GitHub Actions: build image → push a ghcr.io/farox-coop/sales-ai-agent-app:latest

VPS:
  ssh → git pull
  make prod-deploy → docker compose pull app → down → up -d
```
