# AGENTS.md — sales-ai-agent

Agente conversacional con IA que reemplaza formularios estáticos por un diagnóstico adaptativo (~12 preguntas) para leads interesados en adopción de IA. Guía al lead con preguntas dinámicas, accede a conocimiento sobre GenIA (https://genia.coop) y persiste el progreso de cada sesión en PostgreSQL.

## Stack

- **Python 3.12+** con **Chainlit** (UI conversacional, puerto 8000)
- **LangChain / LangGraph** (agente ReAct con tool calling y streaming)
- **PostgreSQL 16** (persistencia de leads e interacciones)
- **Docker Compose** (dev y producción)
- **Nginx + Certbot** (reverse proxy con TLS automático en producción)

## Cómo ejecutar localmente

```bash
cp .env.example .env          # editar con LLM_API_KEY y LLM_BASE_URL reales
make dev                       # build + levanta app y postgres
```

- La app queda en `http://localhost:8000`
- PostgreSQL en `localhost:5432` (user/pass/db: `postgres/postgres/lead_magnet`)
- Hot-reload activo sobre `src/` (flag `--watch`)
- Las migraciones de Alembic corren automáticamente al iniciar

### Comandos útiles (dev)

| Comando | Qué hace |
|---------|----------|
| `make dev` | Build + levantar app y postgres |
| `make down` | Bajar servicios y eliminar volúmenes |
| `make shell` | Shell bash en el contenedor de la app |
| `make db-shell` | Conectarse a PostgreSQL vía psql |
| `make db-reset` | Borrar volúmenes y recrear base desde cero |
| `make scrape-genia` | Scrapear JS bundle de genia.coop para generar artículos OKF |
| `make knowledge-reload` | Verificar cuántos artículos cargó la base de conocimiento |

## Estructura del proyecto

```
src/
├── main.py              # Entrypoint: corre migraciones, importa hooks de Chainlit
├── config.py            # Settings centralizados vía pydantic-settings (lee .env)
├── agent/
│   ├── agent.py         # Crea el ReAct agent de LangGraph, streaming con astream_events v2
│   ├── prompts.py       # System prompt en español rioplatense ("vos")
│   └── tools.py         # 6 tools: registrar_lead, contador_preguntas, listar_articulos,
│                         #   leer_articulo, buscar_cv, generar_resumen
├── chainlit/
│   └── hooks.py         # Hooks de ciclo de vida (@on_chat_start, @on_message, @on_stop)
├── db/
│   ├── models.py        # ORM: leads, interacciones, documentos + enums
│   ├── session.py       # Engine async de SQLAlchemy + session factory
│   ├── queries.py       # CRUD helpers asíncronos
│   └── migrations/      # Migraciones de Alembic (001_initial, 002_plan2)
├── knowledge/
│   └── loader.py        # KnowledgeBase: carga archivos .md con frontmatter YAML (formato OKF)
└── llm/                 # DEPRECADO — solo __pycache__, usar src/agent/ en su lugar

data/
└── knowledge/           # 10 artículos .md con frontmatter YAML (GenIA)

prod/
├── docker-compose.yml           # Stack de producción (app + postgres, sin bind mounts)
├── .env.example                 # Template de variables de entorno de producción
├── DEPLOYMENT.md                # Runbook completo de producción
├── setup-server.sh              # Bootstrap de VPS (instala Docker, UFW, crea network)
└── nginx/
    ├── docker-compose.nginx.yml # Stack nginx + certbot (puertos 80/443)
    ├── nginx.conf               # Config principal de nginx con WebSocket upgrade
    └── conf.d/
        ├── default.conf.template    # HTTP → HTTPS redirect
        └── ssl-app.conf.template    # Reverse proxy HTTPS con seguridad (HSTS, X-Frame-Options, etc.)

plans/                   # 12 documentos de planificación de arquitectura (histórico)
scripts/
├── scrape_genia_to_md.py              # Scraper de genia.coop → artículos OKF
└── test_knowledge_integration.py      # Test de integración del knowledge base
```

## Deploy a producción

La infraestructura de producción usa dos stacks de Docker Compose conectados por la network externa `sales-ai-network`:

```
Internet → nginx:443 → proxy_pass → app:8000 (Chainlit)
              ↑
         certbot (renovación cada 12h)
```

Ambos stacks comparten `sales-ai-network` como red externa.

### Primer deploy

```bash
ssh root@<vps-ip>
git clone <repo> /opt/sales-ai-agent
cd /opt/sales-ai-agent
bash prod/setup-server.sh          # instala Docker, UFW, crea network
cp prod/.env.example prod/.env     # editar con passwords y credenciales reales
make prod-setup                    # build + app + postgres + nginx (HTTP)
make ssl-init                      # obtener certificado Let's Encrypt, activar HTTPS
make prod-status                   # verificar que todo esté Up y healthy
```

### Actualizar

```bash
git pull
make prod-deploy                   # rebuild, recicla app, re-renderiza nginx, reload
```

### Comandos de producción

| Comando | Qué hace |
|---------|----------|
| `make prod-setup` | Deploy inicial completo (HTTP) |
| `make prod-deploy` | Rebuild y deploy de updates |
| `make ssl-init` | Bootstrap de TLS con Let's Encrypt |
| `make prod-status` | Estado de todos los servicios |
| `make prod-logs` | Logs de app + postgres |
| `make nginx-logs SERVICE=certbot` | Logs de nginx o certbot |
| `make prod-down` + `make nginx-down` | Bajar todo |

Ver `prod/DEPLOYMENT.md` para el runbook completo, troubleshooting y variables de entorno.

## Convenciones

- **Idioma**: todo el contenido (prompts, knowledge base, UI, commits) en español con voseo rioplatense
- **Testing**: no hay framework formal. El único test es `scripts/test_knowledge_integration.py` (correr con `docker compose run --rm app python3 scripts/test_knowledge_integration.py`)
- **Migraciones**: Alembic, se ejecutan automáticamente en `src/main.py` al iniciar. Las migraciones existentes son `001_initial` y `002_plan2`
- **Variables de entorno**: `.env` para dev, `prod/.env` para producción. Ambos gitignored, existen templates `.env.example`
- **Dependencias**: duplicadas entre `Dockerfile` y `pyproject.toml` — si cambiás una, actualizá la otra
- **`src/llm/`**: directorio deprecado, no usar. Toda la lógica del agente está en `src/agent/`

## Formato OKF (conocimiento)

Los artículos en `data/knowledge/` usan frontmatter YAML con campos `type`, `title`, `description`, `tags`. Soportan cross-references entre artículos con sintaxis `[[slug]]`. El agente navega el conocimiento con las tools `listar_articulos` y `leer_articulo`.
