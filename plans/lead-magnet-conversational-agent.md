# Plan: Lead Magnet Conversacional con Agente de IA

## Contexto

Las empresas interesadas en adopción de IA suelen llegar mediante formularios estáticos que no capturan matices, tienen alta tasa de abandono y no generan engagement. Queremos reemplazar ese formulario por un **agente conversacional** que:

- Guíe al lead con preguntas adaptativas (máx. ~12) para diagnosticar su uso de IA
- Acceda al conocimiento sobre GenIA (servicios, productos, casos de éxito de genia.coop) como contexto
- Persista el progreso y permita seguimiento de sesiones abandonadas
- Notifique al equipo comercial al completarse
- Sea **provider-agnostic** respecto al LLM (sin vendor lock-in)

El proyecto se desarrollará **desde cero**, primero en local y luego deploy a VPS con Docker Compose.

---

## Índice de planes

Estado de cada plan del proyecto. Este índice se actualiza cuando un plan cambia de estado o se agrega uno nuevo.

| # | Plan | Archivo | Estado | Notas |
|---|------|---------|--------|-------|
| 1 | Foundation — Chat Agent Mínimo | [01-foundation-chat-agent.md](01-foundation-chat-agent.md) | ✅ Implementado | Esqueleto base: Chainlit + PostgreSQL + LLM |
| 2 | Persistencia — Modelo de Datos + Migraciones | [02-persistence.md](02-persistence.md) | ✅ Implementado | Schema completo, Alembic, queries |
| 3 | Flujo de Diagnóstico Completo | [03-diagnostic-flow.md](03-diagnostic-flow.md) | ✅ Implementado | Tool calling loop, 12 preguntas, resumen |
| 4 | Diagnóstico de charla real y mejoras | [04-diagnostico-charla-mejoras.md](04-diagnostico-charla-mejoras.md) | ✅ Implementado | Correcciones de prompt post-charla con Peter |
| 5 | Streaming, latencia y optimización UX | [05-streaming-ux-optimization.md](05-streaming-ux-optimization.md) | 🔧 Parcial | Streaming, tool dedup y fast-path hechos; pooling y skeleton pendientes |
| 6 | Benchmark y selección de modelo LLM | [06-llm-model-benchmark.md](06-llm-model-benchmark.md) | ⚠️ Deprecado | No es prioridad ahora |
| 7 | Base de conocimiento con pgvector | [07-pgvector-rag.md](07-pgvector-rag.md) | ⚠️ Deprecado | Sin documentos reales para indexar. Arquitectura válida para futuro |
| 8 | Migración a LangChain + LangGraph | [08-langchain-migration.md](08-langchain-migration.md) | ✅ Implementado | Agente con `create_react_agent` + `astream_events()` |
| 9 | Conocimiento estático + scraping genia.coop | [09-rag-replacement-static-knowledge.md](09-rag-replacement-static-knowledge.md) | ✅ Implementado | Reemplaza Plan 7. .md en memoria + keyword search + system prompt inline |

Leyenda: ✅ Implementado | 🔧 Parcialmente implementado | ❌ Pendiente | ⚠️ Deprecado

---

## Stack tecnológico

| Capa | Tecnología | Justificación |
|---|---|---|
| Chat UI | [Chainlit](https://docs.chainlit.io/) | Widget de chat profesional, libre de vendor lock-in, hooks para eventos de sesión |
| Framework agente | Python + OpenAI SDK (`AsyncOpenAI`) | `base_url` configurable → Anthropic, OpenAI, Groq, etc. Tool calling nativo |
| LLM | Claude (Anthropic) como default | Mejor calidad conversacional en español para este caso |
| Conocimiento GenIA | Archivos `.md` estáticos cargados en memoria (Plan 9) | Sin infraestructura extra, búsqueda por keyword simple |
| RAG / Vector Store (suspendido) | pgvector + `sentence-transformers` (Plan 7) | Para cuando existan documentos reales que indexar |
| Ingesta de docs (suspendido) | Pipeline offline (PDF, MD, TXT) + scraping (Plan 7) | Suspendido — ver Plan 9 para scraping → .md |
| Base de datos | PostgreSQL 16 | Sesiones, leads, preguntas, respuestas |
| Notificaciones | `python-telegram-bot` + `smtplib` | Telegram para equipo, email para seguimiento |
| Task scheduler | [Celery](https://docs.celeryq.dev/) + Redis | Seguimiento de abandonos, jobs periódicos |
| Infraestructura | Docker + Docker Compose | Dev local y prod con la misma config |
| CI/CD | GitHub Actions | Deploy automático a VPS |

---

## Arquitectura general

**Un solo backend, dos formas de acceso.** La misma app de Chainlit sirve tanto la página de chat dedicada como el widget embebido. Ambas comparten hooks, agente, tools y DB.

```
┌───────────────────────────────────────────────────────┐
│  Opción A: Copilot embebido en genia.coop              │
│  ┌───────────────────────────────────────┐             │
│  │  genia.coop (sitio existente)         │             │
│  │  ┌─────────────────────────────────┐  │             │
│  │  │  Chainlit Copilot (flotante)    │  │             │
│  │  │  🔵 "¿Charlamos sobre IA?"      │  │             │
│  │  └─────────────────────────────────┘  │             │
│  └───────────────────────────────────────┘             │
│                                                       │
│  Opción B: Chat dedicado                              │
│  ┌───────────────────────────────────────┐             │
│  │  chat.genia.coop (URL directa)       │             │
│  │  Interfaz completa de Chainlit       │             │
│  └───────────────────────────────────────┘             │
│                                                       │
│  Ambas → mismo backend, mismo agente, misma DB        │
└───────────────────────────────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│  Chainlit App (Python) — VPS propio (único deploy)    │
│                                                       │
│  ┌──────────────────────────────────────┐            │
│  │  Agente conversacional               │            │
│  │  - System prompt (basado en          │            │
│  │    agency-agents Discovery Coach)    │            │
│  │  - Historial de sesión en DB         │            │
│  │  - Tool calling loop                 │            │
│  └──────────────────────────────────────┘            │
│                                                       │
│  Tools disponibles para el agente:                    │
│  ┌──────────────────────────────────────┐            │
│  │  buscar_documentos(query)                  │            │
│  │    → KnowledgeBase.search()          │            │
│  │    (archivos .md en memoria)         │            │
│  │  buscar_cv(tecnologia)               │            │
│  │    → Stub informativo (sin CVs)      │            │
│  │  registrar_lead(nombre, email, etc.) │            │
│  │    → Crea/actualiza lead en DB       │            │
│  │  contador_preguntas()                │            │
│  │    → Cuántas quedan disponibles      │            │
│  └──────────────────────────────────────┘            │
│                                                       │
│  ┌──────────────────────────────────────┐            │
│  │  Eventos / Hooks                     │            │
│  │  @cl.on_chat_start → init sesión     │            │
│  │    anónima, agente arranca con       │            │
│  │    presentación cálida               │            │
│  │  @cl.on_chat_end   → guardar +       │            │
│  │    notificar completitud              │            │
│  │  @cl.on_stop        → marcar abandono │            │
│  └──────────────────────────────────────┘            │
└──────────────────────────────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│  Servicios auxiliares (Docker)                        │
│                                                       │
│  ┌────────────────────────────────────────┐          │
│  │  PostgreSQL 16                          │          │
│  │  - Tablas: leads, interacciones        │          │
│  │  - Tabla: documentos (vacía,           │          │
│  │    para futuro RAG si hace falta)      │          │
│  └────────────────────────────────────────┘          │
└──────────────────────────────────────────────────────┘

 Conocimiento de GenIA (carga estática al iniciar):
 ┌────────────────────────────────────────────────────┐
 │  data/knowledge/*.md                               │
 │  (archivos generados desde genia.coop)             │
 │       ↓                                            │
 │  src/knowledge/loader.py                           │
 │  (KnowledgeBase con keyword search en memoria)     │
 └────────────────────────────────────────────────────┘
```

---

## Modelo de datos

### `leads`
| Campo | Tipo | Descripción |
|---|---|---|
| id | UUID | PK |
| nombre | str | Del form de identificación |
| email | str | Único, para seguimiento |
| empresa | str? | |
| cargo | str? | |
| estado | enum: `activo`, `completado`, `abandonado` | |
| metadata | JSON | Datos inferidos por el agente (perfiles de usuario, proveedores, etc.) |
| resumen_diagnostico | str? | Texto generado al completar |
| nivel_madurez | enum: `bajo`, `medio`, `alto`? | |
| session_id | str | ID de sesión Chainlit |
| created_at | datetime | |
| updated_at | datetime | |

### `interacciones`
| Campo | Tipo | Descripción |
|---|---|---|
| id | UUID | PK |
| lead_id | FK → leads | |
| rol | enum: `user`, `assistant`, `tool_call` | |
| contenido | text | |
| tool_name | str? | Si es tool_call |
| tool_result | text? | |
| pregunta_numero | int? | Nº de pregunta (1-12) |
| created_at | datetime | |

### `documentos` (metadata de documentos indexados)
| Campo | Tipo | Descripción |
|---|---|---|
| id | UUID | PK |
| drive_id | str? | ID de Google Drive (opcional, si el doc vino de Drive) |
| nombre | str | Nombre del archivo o URL fuente |
| tipo | enum: `propuesta`, `cv`, `presupuesto`, `otro` | |
| mime_type | str? | |
| fuente | str | Origen: `gdrive` o `web` |
| ultima_sincro | datetime | |
| chunks_count | int | |
| status | enum: `activo`, `archivado` | |

---

## Diseño del agente

### System prompt (basado en agency-agents Discovery Coach + Sales Engineer)

El prompt debe incluir:

1. **Personalidad y tono**: consultor empático, profesional, que hace preguntas naturales (no interrogatorio)
2. **Fase 0 — Identificación conversacional** (primeras 2-3 preguntas, de forma natural):
   - "¿Cómo te llamás?" → nombre
   - "¿Me dejás un email por si se corta la charla?" → email
   - "¿De qué empresa me estás hablando?" → empresa
   - Estos datos se persisten vía la tool `registrar_lead` apenas se obtienen
3. **Dominios a explorar** (orden flexible, se adapta):
   - Perfil de la empresa (rubro, tamaño, estructura)
   - Casos de uso actuales de IA (si los hay)
   - Perfiles de usuarios que usan o usarían IA
   - Proveedores y herramientas actuales
   - Infraestructura de datos y base de conocimiento interna
   - Gobernanza y políticas de IA
   - Presupuesto y expectativas de ROI
   - Experiencias previas (qué funcionó, qué no)
4. **Reglas estrictas**:
   - Máximo 12 preguntas de diagnóstico + las 2-3 de identificación = ~15 interacciones totales
   - No repetir información ya proporcionada
   - Si un dominio no aplica, saltearlo
   - Cada 3-4 preguntas, hacer un micro-resumen de validación
   - Al llegar a la pregunta 10 de diagnóstico, avisar que quedan pocas
   - Al finalizar, generar resumen estructurado y guardarlo con `registrar_lead`
5. **Uso de herramientas**:
   - Si el lead pregunta por GenIA (servicios, productos, experiencia) → responder desde el conocimiento inline en el system prompt. Usar `buscar_documentos` como respaldo para búsquedas precisas.
   - Si el lead pregunta por perfiles o experiencia técnica específica → `buscar_cv` informa que no hay CVs indexados; derivar al equipo comercial.
   - Si el lead da datos de identificación (nombre, email, empresa) → `registrar_lead` incrementalmente.

### Loop conversacional

```
┌──────────────┐
│  Usuario     │
│  responde    │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────┐
│  Chainlit recibe mensaje             │
│  → Guarda en DB (interacciones)      │
│  → Construye contexto:               │
│     [system_prompt] + [historial]    │
│     + [datos_lead] + [user_msg]      │
└──────┬───────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  LLM (Anthropic/OpenAI)              │
│  → Decide: responder o usar tool?    │
└──────┬───────────────────────────────┘
       │
  ┌────┴──────────────────┐
  │                        │
  ▼                        ▼
┌────────────┐    ┌──────────────────┐
│ Responder  │    │ Tool call        │
│ (texto)    │    │ → ejecutar tool  │
│            │    │ → volver a LLM   │
│            │    │   con resultado  │
└─────┬──────┘    └──────────────────┘
      │
      ▼
┌──────────────────────────────────────┐
│  Chainlit envía respuesta            │
│  → Guarda en DB                      │
│  → Si es pregunta final → resumen    │
│  → Si es completitud → notificar     │
└──────────────────────────────────────┘
```

---

## Base de conocimiento de GenIA (estática — implementada ✅)

Ver [Plan 9 — Reemplazo de RAG por conocimiento estático](./09-rag-replacement-static-knowledge.md) para el detalle completo de la decisión de arquitectura.

El conocimiento de GenIA se maneja con archivos `.md` estáticos cargados en memoria al iniciar el agente. El contenido (~15KB, ~3,800 tokens) se incluye directamente en el system prompt (Plan 9, Opción A), por lo que el agente responde preguntas sobre GenIA sin necesidad de tool calls. La tool `buscar_documentos` sigue disponible como respaldo para búsquedas precisas con keyword scoring.

El diseño original con pgvector ([Plan 7](./07-pgvector-rag.md)) queda suspendido hasta que existan documentos reales que justifiquen búsqueda semántica vectorial (50+ documentos o 500KB+ de texto).

### Archivos de conocimiento

```
data/knowledge/
├── genia.md                 # Identidad, misión, principios
├── servicios-ia.md          # 5 fases de servicio (Diagnóstico → Acompañamiento)
├── productos.md             # Genway — capa de gobierno de IA
├── casos-de-exito.md        # Sector público, salud, cooperativas
├── industrias.md            # Sectores objetivo y desafíos
├── tecnologias.md           # Stack AI Open Source (6 capas)
└── proceso-de-trabajo.md    # Roadmap + ROI metrics
```

### Pipeline offline

El contenido se extrajo del bundle JS de genia.coop (React SPA hosteada en GitHub Pages). El script `scripts/scrape_genia_to_md.py` extrae el texto del bundle para auditar el contenido actual. Los archivos `.md` se mantienen y editan manualmente.

```bash
# Auditar contenido actual del sitio
curl -sL https://genia.coop/assets/index-3OEbpqcP.js > /tmp/genia_bundle.js
python scripts/scrape_genia_to_md.py /tmp/genia_bundle.js

# Recargar conocimiento en el agente (dentro de Docker)
make knowledge-reload
```

### Fuente de la base de conocimiento

- **Web de GenIA** ([genia.coop](https://genia.coop)): servicios, productos, casos de éxito, información corporativa — extraído del JS bundle.
- Los archivos `.md` se editan manualmente para mantener precisión. El scraping es punto de partida, no fuente definitiva.
- No existen actualmente documentos internos (propuestas, CVs, presupuestos) para indexar.
- Si en el futuro aparecen, se reactiva el diseño de RAG con pgvector ([Plan 7](./07-pgvector-rag.md)).

---

## Notificaciones y seguimiento

### Al completar (on_chat_end)
1. Guardar resumen en `leads.resumen_diagnostico`
2. Actualizar `leads.estado = 'completado'`
3. Enviar email al equipo comercial con resumen
4. Enviar mensaje a Telegram con datos clave + link al detalle

### Al abandonar (on_stop o timeout)
1. Actualizar `leads.estado = 'abandonado'`
2. Celery task agenda recordatorio: si en 24h no volvió → email automático

### Recordatorio de abandono (Celery Beat)
- Corre cada 1h
- Busca leads con `estado = 'abandonado'` que no hayan recibido recordatorio
- Envía email: "Hola [nombre], tu diagnóstico de IA quedó incompleto. ¿Lo retomamos?"
- Marca `recordatorio_enviado = True`

### Dashboard para el equipo (opcional, fase 2)
- Conjunto de endpoints simples o dashboard Chainlit secundario
- Leads completados, abandonados, nivel de madurez, casos de uso detectados

---

## Estructura del proyecto

```
ia-lead-magnet/
├── pyproject.toml              # Dependencias + metadata (uv o poetry)
├── .env.example                # Template de variables de entorno
├── .env                        # Local (gitignored)
├── docker-compose.yml           # Dev: app + postgres
├── docker-compose.prod.yml     # Prod: app + postgres + nginx
├── Dockerfile                   # Multi-stage build
├── nginx/
│   └── nginx.conf              # Proxy inverso para prod
├── Makefile                    # Comandos útiles: make dev, make sync-gdrive, etc.
│
├── src/
│   ├── main.py                 # Entrypoint de Chainlit: chainlit run src/main.py
│   ├── config.py               # Carga de settings desde .env
│   │
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── agent.py            # LangGraph agent singleton + astream_events()
│   │   ├── prompts.py          # System prompt + GenIA knowledge inline
│   │   └── tools.py            # Definición e implementación de tools (@tool decorator)
│   │
│   ├── chainlit/
│   │   ├── __init__.py
│   │   ├── hooks.py            # @cl.on_chat_start (presentación), @cl.on_chat_end, @cl.on_stop
│   │   ├── copilot.py          # Config del Copilot embed (target, trigger, branding)
│   │   ├── custom_ui.py        # Elementos UI custom (avatares, botones, estilos)
│   │   └── .chainlit/
│   │       ├── config.toml     # Config general de Chainlit
│   │       └── copilot.toml    # Config específica del Copilot
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py           # SQLAlchemy / SQLModel
│   │   ├── session.py          # Conexión, session factory
│   │   ├── migrations/         # Alembic migrations
│   │   └── queries.py          # CRUD helpers
│   │
│   ├── knowledge/
│   │   ├── __init__.py
│   │   └── loader.py            # KnowledgeBase: carga .md en memoria, keyword search
│   │
│   ├── notifications/
│   │   ├── __init__.py
│   │   ├── email.py            # smtplib + templates Jinja2
│   │   └── telegram.py         # python-telegram-bot
│   │
│   └── tasks/
│       ├── __init__.py
│       ├── celery_app.py       # Config de Celery
│       ├── sync_task.py        # Tarea periódica: sincronizar GDrive
│       ├── reminder_task.py    # Tarea periódica: recordatorios de abandono
│       └── notification_task.py# Tarea: enviar notificación de completitud
│
├── tests/                      # Pytest
│   ├── test_agent/
│   └── conftest.py
│
├── scripts/
│   ├── scrape_genia_to_md.py  # One-shot: scrapear genia.coop → data/knowledge/*.md
│
└── docs/
    ├── setup.md                # Guía de setup local
    ├── deploy.md               # Guía de deploy a VPS
    └── agent-design.md         # Documentación del diseño del agente
```

---

## Configuración dual (standalone + Copilot)

### CORS

Agregar `genia.coop` y `localhost` en `allow_origins` del `.chainlit/config.toml`:

```toml
[project]
allow_origins = ["https://genia.coop", "http://localhost:*"]
```

### Copilot embed en genia.coop

```html
<!-- En el <head> o antes de </body> de genia.coop -->
<script src="https://chat.genia.coop/copilot/index.js"></script>
<script>
  window.mountChainlitWidget({
    chainlitServer: "https://chat.genia.coop",
    theme: "dark",  // o "light" según branding
  });
</script>
```

### Diferenciación opcional (solo si hace falta)

```python
import chainlit as cl

@cl.on_chat_start
async def start():
    if cl.context.session.client_type == "copilot":
        # Viene del widget en genia.coop
        print("Lead desde el sitio")
    # Mismo agente para ambos
    ...
```

No necesitamos lógica distinta — la diferenciación es solo por si en el futuro queremos métricas separadas. El comportamiento del agente es idéntico.

---

## MVP (fase 1) — Lo mínimo para validar

| Item | Descripción | Prioridad |
|---|---|---|
| Chainlit Copilot funcional (local o embebido) | Widget de chat andando, accesible desde genia.coop | Crítico |
| Identificación conversacional | El agente pide nombre, email, empresa en las primeras preguntas y persiste con `registrar_lead` | Crítico |
| Agente con system prompt base y tool calling loop | Conversación adaptativa funcional | Crítico |
| Contador de preguntas y finalización | Máximo 12 preguntas + resumen final | Crítico |
| DB (SQLite) con modelo `leads` e `interacciones` | Persistencia básica | Crítico |
| Notificación por Telegram al completar | Feedback inmediato al equipo | Alta |
| Deploy local con Docker Compose | `docker compose up` y funciona | Alta |
| Conocimiento de GenIA (archivos .md desde genia.coop) | Info de servicios, productos y casos de éxito disponible para el agente | Media |
| Email de completitud + recordatorio de abandono | Seguimiento automatizado | Media |

---

## Fase 2 — Producción

| Item | Descripción |
|---|---|
| PostgreSQL en reemplazo de SQLite | |
| Deploy a VPS con Docker Compose prod | |
| Nginx reverse proxy + SSL (Let's Encrypt) | |
| Dashboard simple para equipo comercial | |
| Métricas: tasa de completitud, abandono, tiempo medio | |
| Emails de recordatorio personalizados (Jinja2 templates) | |
| Google Drive webhook para sync en tiempo real | |

---

## Variables de entorno

```env
# LLM
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.anthropic.com/v1   # o https://api.openai.com/v1
LLM_MODEL=claude-sonnet-4-20250514
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=0.7

# Chainlit
CHAINLIT_PORT=8000
CHAINLIT_AUTH_SECRET=...

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/lead_magnet
# DATABASE_SYNC_URL=postgresql://user:pass@postgres:5432/lead_magnet  # prod con Alembic

# Notifications
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASS=...
NOTIFICATION_EMAIL=equipo@empresa.com

TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# Celery
CELERY_BROKER_URL=redis://redis:6379/0
```

---

## Referencias e inspiración

- [Agency Agents](https://github.com/msitarzewski/agency-agents) — Especialmente los agentes: `Discovery Coach`, `Sales Engineer`, `Proposal Strategist`
- [chainlit_haystack_example](https://github.com/josx/chainlit_haystack_example) — Arquitectura de referencia Chainlit + agente con herramientas
- [Chainlit Docs](https://docs.chainlit.io/) — Documentación oficial
- [Chainlit Copilot](https://docs.chainlit.io/deploy/copilot) — Widget de chat embebible en sitios externos
- [Claude Tool Use Guide](https://docs.anthropic.com/en/docs/build-with-claude/tool-use) — Tool calling con Anthropic
- [pgvector](https://github.com/pgvector/pgvector) — Vector store como extensión de PostgreSQL (suspendido, ver Plan 7)
- [sentence-transformers](https://www.sbert.net/) — Embeddings multilingües (suspendido, ver Plan 7)

---

## Verificación

Para validar que el MVP funciona:

1. `docker compose up` arranca todos los servicios sin errores
2. **Opción A — Copilot**: Abrir genia.coop → el widget Copilot aparece → click → se abre chat
3. **Opción B — Standalone**: Abrir `http://localhost:8000` → interfaz completa de Chainlit
4. En ambos casos, el agente se presenta y arranca preguntando nombre, email, empresa de forma natural
5. Completar una conversación completa y verificar:
   - Las interacciones se guardan en `leads` e `interacciones`
   - Llega un mensaje a Telegram con el resumen
6. Dejar una conversación a medias, cerrar el navegador:
   - El lead queda en estado `abandonado`
   - El recordatorio se agenda
7. Verificar que `data/knowledge/*.md` existe y tiene contenido preciso de genia.coop ✅
8. Durante la conversación, mencionar una tecnología → el agente conoce GenIA desde el system prompt (sin tool calls) y `buscar_documentos` tiene resultados reales desde `KnowledgeBase` ✅
