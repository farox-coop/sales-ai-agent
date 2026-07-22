# Plan 2: Persistencia — Modelo de Datos Completo + Migraciones

> **Depende de:** Plan 1 (Foundation)
> **Entrega:** Schema completo alineado al plan maestro, Alembic para migraciones, queries robustas

## Objetivo

Completar la capa de datos para que los planes 3, 4 y 5 tengan todo lo que necesitan. El Plan 1 dejó un schema mínimo funcional (`Lead` e `Interaction` con campos básicos). Ahora lo llevamos al schema del plan maestro y agregamos Alembic para manejar migraciones de acá en adelante.

**Importante:** Plan 2 es dueño de **toda** la capa de datos. Los planes 3, 4 y 5 solo consumen lo que acá se define. Nada de `ALTER TABLE` suelto en planes posteriores.

---

## Diagnóstico: qué hay vs qué falta

### `leads` — actual vs objetivo

| Campo | Plan 1 (hoy) | Plan maestro (objetivo) |
|-------|-------------|------------------------|
| id | ✅ UUID | UUID |
| nombre | ✅ | str |
| email | ✅ | str |
| empresa | ✅ | str? |
| cargo | ✅ | str? |
| estado | ✅ activo/completado/abandonado | igual |
| session_id | ✅ | str |
| created_at | ✅ | datetime |
| updated_at | ✅ | datetime |
| **metadata** | ❌ | JSON — datos inferidos (perfiles, proveedores) |
| **resumen_diagnostico** | ❌ | str? — generado al completar |
| **nivel_madurez** | ❌ | enum: bajo/medio/alto |
| **recordatorio_enviado** | ❌ | bool — para Plan 4 (seguimiento) |

### `interacciones` — actual vs objetivo

| Campo | Plan 1 (hoy) | Plan maestro (objetivo) |
|-------|-------------|------------------------|
| id | ✅ UUID | UUID |
| lead_id | ✅ FK | FK |
| rol | ✅ user/assistant | user/assistant/**tool_call** |
| contenido | ✅ Text | Text |
| pregunta_numero | ✅ int? | int? |
| created_at | ✅ | datetime |
| **tool_name** | ❌ | str? — si rol=tool_call |
| **tool_result** | ❌ | text? — si rol=tool_call |

### `documentos` — no existe

Hay que crear la tabla completa. Originalmente pensada para el Plan 7 (RAG con pgvector, ahora suspendido). Actualmente sin uso — el conocimiento de Farox se maneja con archivos .md estáticos (Plan 9). La tabla se mantiene por si en el futuro se reactiva el RAG.

---

## Cambios por archivo

### 1. `src/db/models.py` — Schema completo

**Agregar al enum `MessageRole`:**
```python
class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    tool_call = "tool_call"  # NUEVO
```

**Agregar a `Lead`:**
```python
nivel_madurez: Mapped[str | None]  # enum: bajo, medio, alto
metadata: Mapped[dict | None]      # JSON — perfiles, proveedores, etc.
resumen_diagnostico: Mapped[str | None]
recordatorio_enviado: Mapped[bool]  # default False
```

**Agregar a `Interaction`:**
```python
tool_name: Mapped[str | None]
tool_result: Mapped[str | None]
```

**Nueva clase `Documento`:**
```python
class DocumentType(str, enum.Enum):
    propuesta = "propuesta"
    cv = "cv"
    presupuesto = "presupuesto"
    otro = "otro"

class DocumentStatus(str, enum.Enum):
    activo = "activo"
    archivado = "archivado"

class Documento(Base):
    __tablename__ = "documentos"

    id: UUID (PK)
    drive_id: str
    nombre: str
    tipo: DocumentType
    mime_type: str
    ultima_sincro: datetime
    chunks_count: int
    status: DocumentStatus
```

### 2. `src/db/queries.py` — Nuevas queries

Funciones a agregar:

```python
async def update_lead(session, lead_id, **kwargs) -> Lead
    # Actualiza cualquier campo del lead. Usado por registrar_lead (Plan 3)
    # y por generar_resumen (Plan 3).

async def get_lead_interactions(session, lead_id) -> list[Interaction]
    # Todas las interacciones de un lead, ordenadas por created_at.

async def count_questions(session, lead_id) -> int
    # Cuenta cuántas preguntas de diagnóstico van (rol=assistant, pregunta_numero IS NOT NULL).

async def get_abandoned_leads(session) -> list[Lead]
    # Leads con estado=abandonado y recordatorio_enviado=False. Para Plan 4.

async def mark_reminder_sent(session, lead_id) -> None
    # Pone recordatorio_enviado=True. Para Plan 4.

async def upsert_documento(session, drive_id, **kwargs) -> Documento
    # Insert or update doc metadata. Para Plan 7.

async def get_active_documents(session, tipo=None) -> list[Documento]
    # Docs activos, opcionalmente filtrados por tipo. Para Plan 7.
```

### 3. `src/db/session.py` — Pooling y retry

Agregar configuración de connection pool a `create_async_engine`:

```python
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,       # Verifica que la conexión siga viva
    pool_recycle=3600,        # Recicla conexiones cada 1h
)
```

### 4. Alembic — Migraciones

Inicializar Alembic en el proyecto. Como ya tenemos tablas creadas (Plan 1), la primera migración captura el estado actual.

```bash
# Estructura nueva
src/db/
├── __init__.py
├── models.py
├── session.py
├── queries.py
└── migrations/
    ├── alembic.ini
    ├── env.py
    ├── script.py.mako
    └── versions/
        └── 001_initial.py      # Estado actual (Plan 1)
        └── 002_plan2.py        # Cambios de este plan
```

La migración `002_plan2.py` agrega las columnas nuevas con `ALTER TABLE` y crea la tabla `documentos`.

### 5. `src/main.py` — Usar Alembic en vez de `create_all`

Reemplazar:
```python
Base.metadata.create_all(sync_engine)
```
Por correr migraciones de Alembic programáticamente:
```python
from alembic.config import Config
from alembic import command

alembic_cfg = Config("src/db/migrations/alembic.ini")
command.upgrade(alembic_cfg, "head")
```

Esto asegura que en dev y prod se use el mismo mecanismo.

### 6. `pyproject.toml` — Nueva dependencia

```toml
"alembic>=1.13.0",
```

---

## Archivos a tocar

| Archivo | Acción |
|---------|--------|
| `src/db/models.py` | Completar campos, agregar `Documento` |
| `src/db/queries.py` | 7 funciones nuevas |
| `src/db/session.py` | Pooling config |
| `src/db/migrations/` | **Nuevo**. Alembic init + 2 migraciones |
| `src/main.py` | `create_all` → `command.upgrade` |
| `pyproject.toml` | Agregar `alembic` |
| `Dockerfile` | Copiar `src/db/migrations/` al container |

---

## Verificación

```bash
make dev          # Arranca, aplica migraciones automáticamente

make db-shell     # Verificar schema
\d leads          # Debe mostrar metadata, resumen_diagnostico, nivel_madurez, recordatorio_enviado
\d interacciones  # Debe mostrar tool_name, tool_result
\d documentos     # Debe existir
```

1. `docker compose up` ejecuta migraciones sin errores
2. Las columnas viejas del Plan 1 conservan sus datos (no se pierde nada)
3. Las queries nuevas funcionan: `update_lead`, `count_questions`, `get_abandoned_leads`
4. `make db-reset` borra todo y recrea desde cero vía migraciones

---

## Lo que NO incluye este plan

- Tool calling, `registrar_lead`, `contador_preguntas` → Plan 3
- Notificaciones, Celery, Redis → Plan 4
- Conocimiento estático de Farox → Plan 9
- RAG con pgvector → Plan 7 (suspendido)
- Índices adicionales en DB (se agregan cuando midamos performance)

---

## Notas de implementación (2026-07-20)

### Cambios respecto al plan original

1. **`metadata` → `extra_data`**: el nombre `metadata` es reservado por SQLAlchemy (`Base.metadata`). El campo en la DB y el atributo Python se llaman `extra_data`.

2. **`settings.database_url` → `settings.sqlalchemy_async_url`**: la variable `DATABASE_URL` en `.env` es leída automáticamente por Chainlit para su capa de datos interna (tablas `Thread`, `Step`, etc.). Como nosotros manejamos nuestra propia persistencia, separamos las URLs:
   - `SQLALCHEMY_ASYNC_URL=postgresql+asyncpg://...` (para SQLAlchemy async)
   - `DATABASE_SYNC_URL=postgresql://...` (para Alembic)

3. **`alembic.ini` `script_location`**: debe ser `src/db/migrations` (relativo a `/app` en el container), no `.`.
