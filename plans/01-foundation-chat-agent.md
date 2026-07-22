# Plan 1: Foundation — Chat Agent Mínimo (Local)

> **Depende de:** nada (proyecto desde cero)
> **Entrega:** `docker compose up` → Chainlit + PostgreSQL → chatear con un agente LLM, conversaciones persistidas

## Objetivo

Tener un chat funcional corriendo localmente con Docker Compose, donde un agente conversacional responde usando Claude (Anthropic) via OpenAI SDK. **PostgreSQL como base de datos desde el día 1** (sin SQLite intermedio). Las interacciones y leads se persisten en DB.

El foco es **armar el esqueleto bien**, que después sea fácil agregarle capas.

---

## Lo que se construye

```
ia-lead-magnet/
├── pyproject.toml
├── .env.example
├── .env                          # Local, gitignored
├── Dockerfile                    # Multi-stage
├── docker-compose.yml            # app + postgres
├── .gitignore
├── Makefile

├── src/
│   ├── main.py                   # Entrypoint: chainlit run src/main.py
│   ├── config.py                 # Settings desde .env (pydantic-settings)
│   │
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── prompts.py            # System prompt base
│   │   └── conversation.py       # Loop conversacional
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   └── client.py             # AsyncOpenAI wrapper, provider-agnostic
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py             # SQLAlchemy: Lead, Interaction
│   │   ├── session.py            # AsyncSession factory
│   │   └── queries.py            # CRUD helpers: save_interaction, get_or_create_lead
│   │
│   └── chainlit/
│       ├── __init__.py
│       └── hooks.py              # @cl.on_chat_start, @cl.on_message, @cl.on_chat_end

├── .chainlit/
│   └── config.toml               # Config de Chainlit

└── tests/
    ├── conftest.py
    └── test_agent/
        └── test_conversation.py
```

---

## Paso a paso

### 1. `pyproject.toml` — Dependencias

```toml
[project]
name = "ia-lead-magnet"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "chainlit>=2.0.0",
    "openai>=1.0.0",
    "pydantic-settings>=2.0.0",
    "python-dotenv>=1.0.0",
    "httpx>=0.27.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.30.0",
    "psycopg2-binary>=2.9.0",
]
```

### 2. `src/config.py` — Settings

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    llm_api_key: str
    llm_base_url: str = "https://api.anthropic.com/v1"
    llm_model: str = "claude-sonnet-4-20250514"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.7

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/lead_magnet"
    database_sync_url: str = "postgresql://postgres:postgres@postgres:5432/lead_magnet"

    # Chainlit
    chainlit_port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

### 3. `src/llm/client.py` — Cliente LLM

```python
from openai import AsyncOpenAI
from src.config import settings

client = AsyncOpenAI(
    api_key=settings.llm_api_key,
    base_url=settings.llm_base_url,
)


async def get_llm_response(messages: list[dict]) -> str:
    response = await client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
    )
    return response.choices[0].message.content
```

### 4. `src/db/session.py` — Conexión asíncrona

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from src.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    async with async_session() as session:
        yield session
```

### 5. `src/db/models.py` — Modelos SQLAlchemy

Solo lo esencial para esta fase: `Lead` y `Interaction`. Se mapean al plan maestro pero con campos acotados. En el Plan 2/3 se agregan los campos más específicos (metadata, nivel_madurez, etc.).

```python
import uuid
from datetime import datetime
from sqlalchemy import String, Text, Integer, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum


class Base(DeclarativeBase):
    pass


class LeadStatus(str, enum.Enum):
    activo = "activo"
    completado = "completado"
    abandonado = "abandonado"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    empresa: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cargo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    estado: Mapped[LeadStatus] = mapped_column(Enum(LeadStatus, name="lead_status"), default=LeadStatus.activo)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    interacciones: Mapped[list["Interaction"]] = relationship(back_populates="lead", cascade="all, delete-orphan")


class Interaction(Base):
    __tablename__ = "interacciones"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=True)
    rol: Mapped[MessageRole] = mapped_column(Enum(MessageRole, name="message_role"))
    contenido: Mapped[str] = mapped_column(Text)
    pregunta_numero: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    lead: Mapped["Lead"] = relationship(back_populates="interacciones")
```

### 6. `src/db/queries.py` — CRUD helpers

```python
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Lead, Interaction, MessageRole, LeadStatus


async def get_or_create_lead(session: AsyncSession, session_id: str) -> Lead:
    result = await session.execute(select(Lead).where(Lead.session_id == session_id))
    lead = result.scalar_one_or_none()
    if lead is None:
        lead = Lead(session_id=session_id)
        session.add(lead)
        await session.commit()
        await session.refresh(lead)
    return lead


async def save_interaction(
    session: AsyncSession,
    lead_id: uuid.UUID,
    rol: MessageRole,
    contenido: str,
) -> Interaction:
    interaction = Interaction(lead_id=lead_id, rol=rol, contenido=contenido)
    session.add(interaction)
    await session.commit()
    return interaction


async def close_lead(session: AsyncSession, lead_id: uuid.UUID, status: LeadStatus) -> None:
    lead = await session.get(Lead, lead_id)
    if lead:
        lead.estado = status
        await session.commit()
```

### 7. `src/agent/prompts.py` — System prompt base (MVP)

```python
SYSTEM_PROMPT = """Eres un consultor de IA que conversa con potenciales clientes de GenIA.

Tu objetivo es conocer a la persona y su empresa mediante una conversación natural y empática,
explorando su contexto y posibles necesidades de IA. No sos un formulario: hacé preguntas
de a una, escuchá las respuestas, y mostrá interés genuino.

Tono: profesional pero cálido, en español. Usar "vos" (rioplatense).

Empieza presentándote brevemente y preguntando cómo puede ayudar."""
```

### 8. `src/agent/conversation.py` — Loop conversacional

```python
from src.agent.prompts import SYSTEM_PROMPT
from src.llm.client import get_llm_response


async def process_message(user_message: str, history: list[dict]) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_message},
    ]
    return await get_llm_response(messages)
```

### 9. `src/chainlit/hooks.py` — Hooks con persistencia

```python
import chainlit as cl
from src.agent.conversation import process_message
from src.db.models import MessageRole, LeadStatus
from src.db.queries import get_or_create_lead, save_interaction, close_lead
from src.db.session import async_session


@cl.on_chat_start
async def start():
    # Crear o recuperar lead en DB
    session_id = cl.user_session.get("id") or cl.context.session.id
    cl.user_session.set("session_id", session_id)

    async with async_session() as db:
        lead = await get_or_create_lead(db, session_id)
        cl.user_session.set("lead_id", lead.id)

    # Historial vacio
    cl.user_session.set("history", [])

    # Mensaje de presentación
    from src.agent.prompts import SYSTEM_PROMPT
    from src.llm.client import get_llm_response

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Hola"},
    ]
    greeting = await get_llm_response(messages)
    await cl.Message(content=greeting).send()


@cl.on_message
async def on_message(message: cl.Message):
    history = cl.user_session.get("history", [])
    lead_id = cl.user_session.get("lead_id")

    # Guardar mensaje del usuario en DB
    async with async_session() as db:
        await save_interaction(db, lead_id, MessageRole.user, message.content)

    # Agregar al historial
    history.append({"role": "user", "content": message.content})

    # Respuesta del agente
    response = await process_message(message.content, history)

    # Guardar respuesta en DB
    async with async_session() as db:
        await save_interaction(db, lead_id, MessageRole.assistant, response)

    # Agregar al historial
    history.append({"role": "assistant", "content": response})
    cl.user_session.set("history", history)

    # Enviar respuesta
    await cl.Message(content=response).send()


@cl.on_stop
async def on_stop():
    lead_id = cl.user_session.get("lead_id")
    if lead_id:
        async with async_session() as db:
            await close_lead(db, lead_id, LeadStatus.abandonado)
```

### 10. `src/main.py` — Entrypoint

```python
# Este archivo es el entrypoint para Chainlit.
# Los hooks se importan para que Chainlit los registre.
import src.chainlit.hooks  # noqa: F401
```

### 11. `.chainlit/config.toml`

```toml
[project]
name = "GenIA IA Lead Magnet"

[features]
# Sin autenticación en dev local
```

### 12. `Dockerfile` — Multi-stage

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

FROM python:3.12-slim AS runtime
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY src/ ./src/
COPY .chainlit/ ./.chainlit/
EXPOSE 8000
CMD ["chainlit", "run", "src/main.py", "--host", "0.0.0.0", "--port", "8000"]
```

### 13. `docker-compose.yml` — App + PostgreSQL

```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./src:/app/src
    command: chainlit run src/main.py --host 0.0.0.0 --port 8000 --watch
    depends_on:
      postgres:
        condition: service_healthy

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: lead_magnet
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d lead_magnet"]
      interval: 3s
      timeout: 3s
      retries: 5

volumes:
  pgdata:
```

### 14. `.env.example` + `.env`

```env
# LLM
LLM_API_KEY=sk-ant-...
LLM_BASE_URL=https://api.anthropic.com/v1
LLM_MODEL=claude-sonnet-4-20250514
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=0.7

# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/lead_magnet
DATABASE_SYNC_URL=postgresql://postgres:postgres@postgres:5432/lead_magnet

# Chainlit
CHAINLIT_PORT=8000
```

### 15. `Makefile`

```makefile
.PHONY: dev build down shell db-reset

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
```

### 16. `.gitignore`

```
.env
__pycache__/
*.pyc
.venv/
data/
.chainlit/translations/
pgdata/
```

---

## Verificación

Para validar que este plan funciona:

1. Crear `.env` con una API key de Anthropic válida
2. `make dev` → los logs muestran "Your app is available at http://localhost:8000"
3. `docker compose logs postgres` → PostgreSQL está healthy
4. Abrir `http://localhost:8000` → se ve la interfaz de Chainlit
5. El agente se presenta con un saludo cálido
6. Escribir un mensaje → el agente responde en español, tono consultivo
7. Ejecutar `make db-shell` y verificar que las tablas `leads` e `interacciones` tienen datos
8. Cerrar el navegador → el lead queda en estado `abandonado`

---

## Lo que NO incluye este plan

- Tools / tool calling (registrar_lead, buscar_documentos, etc.) → Plan 3
- System prompt completo con flujo de diagnóstico (12 preguntas) → Plan 3
- Notificaciones (Telegram, email) → Plan 4
- Celery + Redis → Plan 4
- Conocimiento estático de GenIA (archivos .md) → Plan 9
- RAG con pgvector → Plan 7 (suspendido, no hay documentos para indexar)
- Copilot embed, deploy, SSL → plan futuro (Plan 6 original deprecado)

---

## Notas post-implementación

- **Saludo hardcodeado**: El `on_chat_start` ya no llama al LLM — usa un `GREETING` fijo para ser instantáneo (ver `hooks.py`).
- **Sin `.chainlit/config.toml`**: Se borró. Chainlit 2.x regenera su config con defaults. Cualquier customización va por variables de entorno.
- **Dockerfile single-stage**: Simplificado, instala dependencias directo con pip y usa `PYTHONPATH=/app`.
- **System prompt con cierre temporal**: Se agregó sección "Cierre de la conversación" como parche. Será reemplazada en el Plan 3.

---

## Notas de diseño

- **PostgreSQL directo**: Nos salteamos SQLite. El `docker-compose.yml` incluye PostgreSQL 16. En dev local funciona igual que en prod.
- **Provider-agnostic**: `AsyncOpenAI` con `base_url` configurable. Para Anthropic: `https://api.anthropic.com/v1`. Para OpenAI: `https://api.openai.com/v1`.
- **Las tablas se crean automáticamente**: Cuando arranca la app, `Base.metadata.create_all` crea las tablas si no existen (esto se hace en `main.py` o en un evento de startup).
- **Estructura plana**: Sin over-engineering. A medida que crezca, se refactoriza.
