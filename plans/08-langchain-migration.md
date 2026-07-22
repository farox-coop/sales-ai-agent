# Plan 8: Migración del Agente a LangChain + LangGraph

> **Depende de:** Plan 1-5 completados (agente con tools, streaming, DB)
> **Entrega:** agente funcionando con `create_react_agent` + streaming granular via `astream_events()`

## Objetivo

Reemplazar el loop manual de tool calling + streaming artesanal (`conversation.py`, `client.py`, `tools.py`, `tool_handlers.py` — ~710 líneas) por el stack LangChain + LangGraph, apuntando al AI gateway de GenIA como provider único.

**Motivaciones:**
- Las tools se definen con `@tool` decorator → schema JSON inferido automáticamente
- El loop de tool calling es una línea: `agent.astream_events()`
- El streaming es granular: tokens, `on_tool_start`, `on_tool_end` → mejor UX en Chainlit
- LangGraph soporta human-in-the-loop, multi-agent y branching para el futuro
- El AI gateway hace irrelevante el vendor lock-in: `ChatOpenAI` con `base_url` configurable alcanza para todo

---

## Stack resultante

| Capa | Antes | Después |
|---|---|---|
| Agente + tools + loop | SDK OpenAI a pelo (~710 líneas) | `langgraph` (`create_react_agent`) + `langchain_core.tools` |
| Cliente LLM | `openai.AsyncOpenAI` | `langchain_openai.ChatOpenAI` → AI gateway |
| Streaming | Loop manual con deltas | `.astream_events(version="v2")` |
| Prompts | `SYSTEM_PROMPT` con docs de tools inline | `SystemMessage` + schemas auto-generados |
| Conocimiento GenIA (Plan 9) | .md estáticos + keyword search | Igual (no usa LangChain) |
| RAG (suspendido, Plan 7) | pgvector + chunker propio | `langchain-text-splitters` + `langchain-postgres` |

**Lo que NO cambia:** DB (`SQLAlchemy` + `asyncpg`), Chainlit UI, notificaciones, Celery, config base.

---

## Arquitectura final

```
hooks.py (Chainlit)
  │
  ├─ @cl.on_chat_start → crear lead en DB, init historial
  │
  └─ @cl.on_message → agent.astream_events({"messages": [...]}, config={...})
       │
       ├─ kind == "on_chat_model_stream"
       │   → msg.stream_token(token)                  ← streaming en vivo
       │
       ├─ kind == "on_tool_start"
       │   → msg.stream_token("🔍 Buscando...")       ← skeleton UI
       │
       └─ kind == "on_tool_end"
           → msg.stream_token(resultado)              ← opcional: mostrar resultado

agent.py (nuevo)
  │
  └─ create_react_agent(
       model=ChatOpenAI(base_url=gateway, model=...),
       tools=[registrar_lead, contador_preguntas, buscar_documentos, ...],
       prompt=SystemMessage(SYSTEM_PROMPT),
     )

tools.py (reescrito)
  │
  ├─ @tool async def registrar_lead(nombre, email, ...)
  │    → usa RunnableConfig para obtener db + lead_id
  ├─ @tool async def contador_preguntas()
  ├─ @tool async def buscar_documentos(query, tipo?)
  ├─ @tool async def buscar_cv(tecnologia)
  └─ @tool async def generar_resumen()
```

---

## Paso a paso

### Paso 1: Dependencias

**Agregar a `pyproject.toml`:**
```toml
dependencies = [
    # ... las existentes se mantienen ...
    "langgraph>=0.2.0",           # create_react_agent, astream_events
    "langchain-core>=0.3.0",      # @tool, SystemMessage, RunnableConfig
    "langchain-openai>=0.2.0",    # ChatOpenAI (apunta al gateway)
]
```

**Remover:**
```toml
# "openai>=1.0.0",  ← ya no se usa directamente
```

`httpx` se mantiene (Chainlit lo usa). `openai` como paquete se elimina — `langchain-openai` lo trae como dependencia transitiva de todas formas.

---

### Paso 2: Nuevo `src/agent/tools.py`

Reescribir completamente. Cada tool es una función decorada con `@tool` de `langchain_core.tools`.

**Patrón de inyección de dependencias:** las tools necesitan `db` (AsyncSession) y `lead_id` (UUID) para operar. Estos NO son parámetros que el LLM deba pasar — son contexto de ejecución. Se usa `RunnableConfig`:

```python
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

@tool
async def registrar_lead(
    nombre: str = "",
    email: str = "",
    empresa: str = "",
    cargo: str = "",
    config: RunnableConfig = None,
) -> str:
    """Registra o actualiza los datos de identificación del lead en la base de datos.

    Llamala SOLO cuando el lead proporcione un dato NUEVO que no hayas registrado
    antes. No la llames por las dudas o 'para verificar'.

    Args:
        nombre: Nombre completo del lead.
        email: Correo electrónico del lead.
        empresa: Nombre de la empresa donde trabaja.
        cargo: Cargo o rol del lead en la empresa.
    """
    db = config["configurable"]["db"]
    lead_id = config["configurable"]["lead_id"]
    # ... misma lógica que hoy en handle_registrar_lead ...
```

Cada tool actual se convierte así:

| Tool actual (dict + handler) | Nueva tool (`@tool`) |
|---|---|
| `TOOLS[0]` + `handle_registrar_lead` | `@tool async def registrar_lead(...)` |
| `TOOLS[1]` + `handle_contador_preguntas` | `@tool async def contador_preguntas(...)` |
| `TOOLS[2]` + `handle_buscar_documentos` | `@tool async def buscar_documentos(...)` |
| `TOOLS[3]` + `handle_buscar_cv` | `@tool async def buscar_cv(...)` |
| `TOOLS[4]` + `handle_generar_resumen` | `@tool async def generar_resumen(...)` |

**Archivos que desaparecen:**
- `src/agent/tool_handlers.py` (~220 líneas) — la lógica se mueve al cuerpo de cada `@tool`

---

### Paso 3: Nuevo `src/agent/prompts.py`

El system prompt actual incluye documentación detallada de tools ("### `registrar_lead(nombre, email, empresa, cargo?)`..."). Con LangChain, los schemas JSON se generan automáticamente de los type hints y docstrings de las tools.

El nuevo `SYSTEM_PROMPT` se simplifica: **solo personalidad, tono, reglas de la conversación y dominios a explorar**. Las descripciones de parámetros viven en los docstrings de cada `@tool`.

Ejemplo del nuevo prompt:
```
Eres un consultor de IA de GenIA que conversa con potenciales clientes...

Tono: profesional pero cálido, en español. Usá "vos" (rioplatense).

## Reglas
- Máximo 12 preguntas de diagnóstico + 2-3 de identificación
- No repetir información ya proporcionada
- Cada 3-4 preguntas, hacer un micro-resumen de validación
- Al llegar a la pregunta 10, avisar que quedan pocas
- Al finalizar, llamar a generar_resumen y mostrar el diagnóstico

## Dominios a explorar
1. Perfil de la empresa (rubro, tamaño)
2. Casos de uso actuales de IA
3. Perfiles de usuarios que usan o usarían IA
...
```

---

### Paso 4: Nuevo `src/agent/agent.py`

Archivo nuevo que encapsula la creación del agente y la ejecución con streaming.

```python
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from src.config import settings
from src.agent.tools import ALL_TOOLS
from src.agent.prompts import SYSTEM_PROMPT

def build_agent():
    """Crea el agente React con tools y modelo configurado."""
    model = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
    return create_react_agent(
        model=model,
        tools=ALL_TOOLS,
        prompt=SystemMessage(content=SYSTEM_PROMPT),
    )

# Singleton: el agente se crea una vez, se reusa por request
agent = build_agent()

async def run_agent_streaming(
    user_message: str,
    history: list[dict],
    db,
    lead_id,
    stream_callback,
    tool_callback,
):
    """Ejecuta el agente con streaming granular.

    Emite eventos a los callbacks:
    - stream_callback(token) → para cada token de texto
    - tool_callback(event_type, tool_name) → on_tool_start / on_tool_end
    """
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        *_dict_history_to_langchain(history),
        HumanMessage(content=user_message),
    ]

    config = RunnableConfig(configurable={"db": db, "lead_id": lead_id})

    async for event in agent.astream_events(
        {"messages": messages},
        config=config,
        version="v2",
    ):
        kind = event["event"]

        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                await stream_callback(chunk.content)

        elif kind == "on_tool_start":
            name = event.get("name", "")
            await tool_callback("start", name)

        elif kind == "on_tool_end":
            name = event.get("name", "")
            await tool_callback("end", name)

    # Extraer la respuesta final de los mensajes del estado
    # ...

def _dict_history_to_langchain(history: list[dict]) -> list:
    """Convierte historial en formato dict a mensajes LangChain."""
    mapping = {
        "user": HumanMessage,
        "assistant": AIMessage,
        "system": SystemMessage,
    }
    return [
        mapping[m["role"]](content=m["content"])
        for m in history
        if m["role"] in mapping
    ]
```

**Archivos que desaparecen:**
- `src/llm/client.py` (~137 líneas) — reemplazado por `ChatOpenAI`
- `src/llm/__init__.py` — todo el directorio `src/llm/` desaparece
- `src/agent/conversation.py` (~224 líneas) — reemplazado por `agent.astream_events()`

---

### Paso 5: Adaptar `src/chainlit/hooks.py`

La estructura se simplifica. El `on_message` pasa de manejar manualmente el historial + loop + streaming a delegar en `run_agent_streaming()`:

```python
import chainlit as cl
from src.agent.agent import run_agent_streaming
from src.db.models import MessageRole, LeadStatus
from src.db.queries import get_or_create_lead, save_interaction, close_lead, count_questions
from src.db.session import async_session

GREETING = "¡Hola! Soy el consultor de IA de GenIA..."
TRIVIAL_RESPONSES = {...}  # se mantiene igual

@cl.on_chat_start
async def start():
    # ... igual que ahora ...
    cl.user_session.set("history", [
        {"role": "assistant", "content": GREETING},
    ])
    await cl.Message(content=GREETING).send()

@cl.on_message
async def on_message(message: cl.Message):
    history = cl.user_session.get("history", [])
    lead_id = cl.user_session.get("lead_id")

    # Fast-path para mensajes triviales se mantiene igual
    ...

    msg = cl.Message(content="")
    await msg.send()

    tool_placeholder_sent = False

    async def stream_token(token: str):
        await msg.stream_token(token)

    async def tool_callback(event_type: str, tool_name: str):
        nonlocal tool_placeholder_sent
        if event_type == "start" and not tool_placeholder_sent:
            tool_placeholder_sent = True
            await msg.stream_token(f"\n🔍 {tool_name}...\n")
        elif event_type == "end":
            pass  # opcional: mostrar confirmación

    async with async_session() as db:
        await save_interaction(db, lead_id, MessageRole.user, message.content)
        history.append({"role": "user", "content": message.content})

        response = await run_agent_streaming(
            message.content, history, db, lead_id,
            stream_callback=stream_token,
            tool_callback=tool_callback,
        )

        pregunta_numero = await count_questions(db, lead_id) + 1
        await save_interaction(
            db, lead_id, MessageRole.assistant, response,
            pregunta_numero=pregunta_numero,
        )

    history.append({"role": "assistant", "content": response})
    cl.user_session.set("history", history)
    await msg.update()

@cl.on_stop
async def on_stop():
    # ... igual que ahora ...
```

---

### Paso 6: Actualizar `src/config.py`

Mínimo cambio: renombrar variables para reflejar el AI gateway:

```python
class Settings(BaseSettings):
    # LLM via AI Gateway
    llm_api_key: str                           # gateway API key
    llm_base_url: str = "https://ai-gateway.genia.coop/v1"  # endpoint OpenAI-compatible
    llm_model: str = "claude-sonnet-4-20250514"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.7

    # Database
    sqlalchemy_async_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/lead_magnet"
    database_sync_url: str = "postgresql://postgres:postgres@postgres:5432/lead_magnet"

    # Chainlit
    chainlit_port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
```

---

### Paso 7: Limpiar archivos obsoletos

Eliminar:
- `src/llm/__init__.py`
- `src/llm/client.py`
- `src/agent/conversation.py`
- `src/agent/tool_handlers.py`
- `src/llm/` (directorio completo)

`src/agent/tools.py` se pisa completamente.

**Balance neto de líneas:**

| Archivo | Antes | Después |
|---|---|---|
| `tools.py` | 130 | ~150 (tools con `@tool`) |
| `tool_handlers.py` | 224 | 0 (eliminado) |
| `conversation.py` | 224 | 0 (eliminado) |
| `client.py` | 137 | 0 (eliminado) |
| `agent.py` (nuevo) | 0 | ~80 |
| `prompts.py` | ~80 | ~60 (simplificado) |
| `hooks.py` | 132 | ~100 (simplificado) |
| **Total** | **~927** | **~390** |

Reducción neta: **~540 líneas** (58% menos).

---

### Paso 8: Actualizar `.env` / `.env.example`

```env
# LLM via AI Gateway
LLM_API_KEY=sk-gateway-...
LLM_BASE_URL=https://ai-gateway.genia.coop/v1
LLM_MODEL=claude-sonnet-4-20250514
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=0.7

# ... resto igual ...
```

---

## Fases futuras (no incluidas en este plan)

### Fase 8B — Chunking con `langchain-text-splitters` (suspendido)

~~Reemplazar chunker propio (`src/rag/chunker.py`) por `RecursiveCharacterTextSplitter`, `MarkdownHeaderTextSplitter` y `SemanticChunker` de `langchain-text-splitters`.~~ **Suspendido junto con Plan 7.** No hay documentos para chunkear.

### Fase 8C — Ingesta con loaders de `langchain-community` (suspendido)

~~Reemplazar parseo manual de PDF/MD/TXT/web en los scripts de ingesta por `PyPDFLoader`, `UnstructuredMarkdownLoader`, `TextLoader`, `AsyncHtmlLoader`.~~ **Suspendido junto con Plan 7.** El conocimiento ahora es estático (archivos .md, Plan 9).

### Fase 8D — Human-in-the-loop

Agregar confirmación antes de ejecutar `generar_resumen` o `registrar_lead` (datos sensibles). LangGraph lo soporta nativamente con interrupts:

```python
# En la definicion del grafo, antes de ciertas tools:
graph.add_node("confirm", human_approval_node)
graph.add_edge("agent", "confirm")
graph.add_conditional_edges("confirm", ...)
```

### Fase 8E — Multi-agent swarm

Si en el futuro el agente necesita derivar a un especialista (ej: agente técnico para preguntas de implementación vs agente comercial para pricing), LangGraph lo permite con handoffs entre agentes, cada uno con sus propias tools.

---

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| `create_react_agent` no expone el resultado final de forma obvia en streaming | Se extrae del último `AIMessage` en `state["messages"]` al terminar el stream |
| `RunnableConfig` puede no fluir correctamente a tools asíncronas | Probar con un tool dummy primero; si falla, usar `contextvars` como plan B |
| El system prompt simplificado puede degradar la calidad del agente | Medir con una conversación de prueba antes/después; iterar sobre el prompt |
| Cambios en la API de LangGraph entre versiones | Fijar versiones con `>=0.2.0,<1.0` hasta estabilizar |

---

## Rollback

Si la migración no funciona:
1. `git revert` al commit anterior
2. El único estado persistente está en DB (leads, interacciones) — no se modifica
3. Las variables de entorno son compatibles hacia atrás (solo cambió el default de `LLM_BASE_URL`)

---

## Verificación

1. `docker compose up` arranca sin errores
2. El agente se presenta y conversa con el mismo tono que antes
3. Las 5 tools funcionan: `registrar_lead`, `contador_preguntas`, `buscar_documentos`, `buscar_cv`, `generar_resumen`
4. El streaming muestra tokens en vivo en Chainlit
5. Cuando el LLM ejecuta tools sin texto previo, se muestra "🔍 nombre_tool..."
6. Las interacciones se persisten correctamente en `interacciones`
7. El contador de preguntas respeta el máximo de 12
8. `generar_resumen` marca el lead como `completado` y el LLM genera el resumen
9. Hacer una conversación de prueba completa y comparar calidad antes/después
