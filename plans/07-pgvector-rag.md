# Plan 7 — Base de conocimiento con pgvector ⚠️ DEPRECADO (julio 2026)

> **Estado:** DEPRECADO. Reemplazado por [Plan 9](09-rag-replacement-static-knowledge.md) (IMPLEMENTADO ✅).
>
> **Motivo:** No existen documentos técnicos, CVs ni presupuestos para indexar.
> El único contenido disponible es el sitio web https://genia.coop, cuyo volumen
> (~10-20 páginas) no justifica una pipeline de RAG con pgvector.
>
> **Qué se implementó en su lugar (Plan 9):**
> - Archivos `.md` estáticos en `data/knowledge/` con contenido de genia.coop
> - `src/knowledge/loader.py` con `KnowledgeBase` — keyword search en memoria
> - El conocimiento se incluye inline en el system prompt (~15KB, ~3,800 tokens)
> - `buscar_documentos` usa `KnowledgeBase.search()` en vez de pgvector
> - `buscar_cv` es un stub honesto (no hay CVs indexados)
>
> **Futuro:** Este diseño se reactivará si GenIA genera documentos reales (propuestas,
> documentación técnica, CVs, papers) en volumen suficiente para justificar búsqueda
> semántica vectorial (50+ documentos o 500KB+ de texto). La arquitectura sigue siendo válida.

**Fecha:** 2026-07-21
**Depende de:** Plan 2 (persistencia — la tabla `documentos` ya existe)
**Reemplaza:** El diseño original con Qdrant + Google Drive sync (ahora descartado)

---

## 1. Cambio de estrategia

### Diseño original (descartado)
- Qdrant (container Docker aparte) como vector store
- Google Drive sync automático con Celery cada 6h
- `google-api-python-client`, extractores de PDF/DOCX, chunking
- Complejidad: 1 container extra, OAuth de Google, Celery + Redis

### Nuevo diseño
- **pgvector** como vector store, dentro de PostgreSQL (ya en uso)
- **Pipeline offline manual**: el operador baja archivos de Google Drive (PDF, MD, TXT) y corre un script que los chunkea, embeddea y guarda en pgvector
- **Scraping de genia.coop**: script que scrapea la web de GenIA y la indexa en pgvector
- **Cero infraestructura nueva**: mismo PostgreSQL, misma conexión asyncpg, mismo ORM

### ¿Por qué pgvector?
1. Ya tenemos PostgreSQL 16 corriendo — es literalmente `CREATE EXTENSION vector`
2. La tabla `documentos` ya existe (migración `002_plan2.py`) con campos para trackear metadatos
3. Escala es chica (cientos de documentos, no millones) — pgvector maneja esto sin problemas
4. ChromaDB queda como mejora futura si llegamos a necesitar hybrid search (BM25 + vectorial)

---

## 2. Arquitectura

```
┌──────────────────────────────────────────────────────────────────┐
│  Pipeline offline (ejecutado manualmente por el operador)         │
│                                                                   │
│  1. docs/                        2. web/                         │
│     Archivos que el operador         genia.coop                  │
│     descargó de Google Drive         (scraping)                  │
│     (PDF, MD, TXT)                   ↓ httpx + BeautifulSoup     │
│     ↓ extract_text()                 contenido HTML → texto      │
│     texto plano                      limpio                      │
│     ↓                                                             │
│  3. Chunking (semantic splitter)                                  │
│     ↓                                                             │
│  4. Embeddings (sentence-transformers)                            │
│     ↓                                                             │
│  5. Upsert en PostgreSQL (pgvector)                               │
│     └→ tabla documentos (metadatos) + tabla document_chunks       │
│         (chunks con su vector)                                    │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  Runtime: el agente usa buscar_documentos() / buscar_cv()        │
│                                                                   │
│  tool_handler → embed query → pgvector similarity search          │
│              → devuelve chunks relevantes → LLM los usa           │
│                                                                   │
│  Query SQL (ejemplo):                                             │
│  SELECT chunk_text, 1 - (embedding <=> query_embedding) AS sim   │
│  FROM document_chunks                                            │
│  WHERE doc_type = 'propuesta'                                    │
│  ORDER BY embedding <=> query_embedding                          │
│  LIMIT 5;                                                        │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Modelo de datos

### Tabla existente: `documentos` (ya creada en Plan 2)

Sin cambios. Sigue trackeando metadatos de cada documento fuente.

### Nueva tabla: `document_chunks`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | UUID | PK |
| documento_id | FK → documentos.id | Documento fuente del chunk |
| chunk_index | int | Posición del chunk dentro del doc |
| chunk_text | text | Texto del chunk |
| embedding | vector(384) | Vector del embedding (dimensión del modelo) |
| token_count | int? | Cantidad de tokens (info, para debug) |
| created_at | datetime | |

### Extensión pgvector

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Tabla `documentos` — ajuste menor

Agregar campo `fuente` para distinguir origen:

```sql
ALTER TABLE documentos ADD COLUMN fuente VARCHAR(50) DEFAULT 'gdrive';
-- valores: 'gdrive', 'web' (genia.coop)
```

---

## 4. Pipeline offline

### 4.1 Estructura de archivos

```
src/rag/
├── __init__.py
├── embedder.py          # Wrapper de sentence-transformers
├── chunker.py           # Semantic chunking (usa modelo de oraciones)
├── indexer.py           # Indexa docs → chunks → embeddings → pgvector
├── retriever.py         # Búsqueda semántica (usado por tool_handlers)
└── scraper.py           # Scraping de genia.coop

scripts/
├── index_docs.py        # Pipeline offline: indexar carpeta de documentos
├── scrape_genia.py      # Pipeline offline: scrapear genia.coop e indexar
└── rebuild_index.py     # Reindexar todo desde cero (útil para cambiar modelo)
```

### 4.2 Dependencias nuevas

```toml
# pyproject.toml
"pgvector>=0.3.0",           # Cliente Python para pgvector
"sentence-transformers>=3.0.0",  # Embeddings
"beautifulsoup4>=4.12.0",   # Scraping de genia.coop
"lxml>=5.0.0",              # Parser HTML (más rápido que html.parser)
"pypdf>=5.0.0",             # Extraer texto de PDFs
```

### 4.3 Flujo de indexación

```python
# scripts/index_docs.py (pseudocódigo)
from src.rag.embedder import Embedder
from src.rag.chunker import chunk_text
from src.rag.indexer import index_document

async def main(docs_dir: str):
    embedder = Embedder(model_name="intfloat/multilingual-e5-small")
    # o "hiiamsid/sentence_similarity_spanish_es" para español

    for filepath in glob(f"{docs_dir}/**/*"):
        text = extract_text(filepath)  # pypdf para PDF, open() para MD/TXT
        chunks = chunk_text(text, max_tokens=300, overlap=50)

        doc = await upsert_documento(db, nombre=filepath.name, fuente="gdrive", ...)

        for i, chunk in enumerate(chunks):
            embedding = embedder.embed(chunk)
            await insert_chunk(db, doc.id, i, chunk, embedding)
```

### 4.4 Flujo de scraping de genia.coop

```python
# scripts/scrape_genia.py (pseudocódigo)
async def main():
    urls = [
        "https://genia.coop",
        "https://genia.coop/servicios",
        "https://genia.coop/casos-de-exito",
        # ...
    ]

    for url in urls:
        html = await fetch(url)
        text = extract_text_from_html(html)  # BeautifulSoup, saca nav, footer, etc.
        chunks = chunk_text(text)
        doc = await upsert_documento(db, nombre=url, fuente="web", ...)

        for i, chunk in enumerate(chunks):
            embedding = embedder.embed(chunk)
            await insert_chunk(db, doc.id, i, chunk, embedding)
```

---

## 5. Modelo de embeddings

### Opción A: `intfloat/multilingual-e5-small` (recomendado)
- 384 dimensiones → vector ocupa ~1.5KB por chunk
- Multilenguaje, buen rendimiento en español
- Modelo chico (~120MB), rápido en CPU
- Licencia MIT

### Opción B: `hiiamsid/sentence_similarity_spanish_es`
- Especializado en español
- 768 dimensiones → más preciso pero más grande

### Elección: Opción A para empezar. Si la calidad semántica es pobre en español, cambiar a B (requiere reindexar).

---

## 6. Búsqueda semántica (runtime)

### `src/rag/retriever.py`

```python
from src.rag.embedder import Embedder
from sqlalchemy import text

embedder = Embedder()

async def search_documents(
    db: AsyncSession,
    query: str,
    tipo: str | None = None,
    limit: int = 5,
    threshold: float = 0.5,
) -> list[dict]:
    query_embedding = embedder.embed(query)

    if tipo:
        results = await db.execute(
            text("""
                SELECT dc.chunk_text, d.nombre, d.tipo,
                       1 - (dc.embedding <=> :embedding) AS similarity
                FROM document_chunks dc
                JOIN documentos d ON dc.documento_id = d.id
                WHERE d.tipo = :tipo AND d.status = 'activo'
                ORDER BY dc.embedding <=> :embedding
                LIMIT :limit
            """),
            {"embedding": query_embedding, "tipo": tipo, "limit": limit},
        )
    else:
        results = await db.execute(
            text("""
                SELECT dc.chunk_text, d.nombre, d.tipo,
                       1 - (dc.embedding <=> :embedding) AS similarity
                FROM document_chunks dc
                JOIN documentos d ON dc.documento_id = d.id
                WHERE d.status = 'activo'
                ORDER BY dc.embedding <=> :embedding
                LIMIT :limit
            """),
            {"embedding": query_embedding, "limit": limit},
        )

    return [
        {"text": row.chunk_text, "source": row.nombre, "tipo": row.tipo, "score": row.similarity}
        for row in results
        if row.similarity >= threshold
    ]
```

---

## 7. Integración con tool_handlers existente

Los stubs `handle_buscar_documentos` y `handle_buscar_cv` en `src/agent/tool_handlers.py` (líneas ~118 y ~142) se reemplazan para usar `retriever.search_documents()`:

```python
# buscar_documentos (línea ~118)
async def handle_buscar_documentos(db, args):
    query = args["query"]
    tipo = args.get("tipo")
    results = await search_documents(db, query, tipo=tipo, limit=3)

    if not results:
        return {"status": "ok", "encontrados": 0, "resultados": [],
                "msg": "No encontré documentos relevantes."}

    return {"status": "ok", "encontrados": len(results),
            "resultados": results,
            "msg": f"Encontré {len(results)} documentos relevantes."}
```

---

## 8. Migración de DB

Nueva migración `003_pgvector.py`:

```python
# alembic/versions/003_pgvector.py
def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column("documentos", sa.Column("fuente", sa.String(50),
                  server_default="gdrive"))

    op.create_table("document_chunks",
        sa.Column("id", UUID, primary_key=True, default=uuid.uuid4),
        sa.Column("documento_id", UUID, ForeignKey("documentos.id"), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(384)),
        sa.Column("token_count", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, default=datetime.utcnow),
    )

    # Índice para búsqueda por similitud (IVFFlat para empezar)
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding "
        "ON document_chunks USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 10)"
    )
```

---

## 9. Archivos involucrados

| Archivo | Acción |
|---------|--------|
| `pyproject.toml` | Agregar `pgvector`, `sentence-transformers`, `beautifulsoup4`, `lxml`, `pypdf` |
| `src/db/models.py` | Agregar modelo `DocumentChunk` y campo `fuente` en `Documento` |
| `src/db/queries.py` | Agregar `insert_chunk()`, `delete_chunks_by_doc()` |
| `src/db/migrations/versions/003_pgvector.py` | **Nuevo**. Extensión vector + tabla document_chunks + índice |
| `src/rag/__init__.py` | **Nuevo** |
| `src/rag/embedder.py` | **Nuevo**. Wrapper de sentence-transformers con lazy loading |
| `src/rag/chunker.py` | **Nuevo**. Semantic chunking |
| `src/rag/indexer.py` | **Nuevo**. Indexa docs en pgvector |
| `src/rag/retriever.py` | **Nuevo**. Búsqueda semántica |
| `src/rag/scraper.py` | **Nuevo**. Scraping de genia.coop |
| `src/agent/tool_handlers.py` | Reemplazar stubs de buscar_documentos/buscar_cv con retriever real |
| `scripts/index_docs.py` | **Nuevo**. Pipeline offline para indexar archivos locales |
| `scripts/scrape_genia.py` | **Nuevo**. Pipeline offline para scrapear genia.coop |
| `scripts/rebuild_index.py` | **Nuevo**. Reindexar todo desde cero |

---

## 10. Verificación

1. `docker compose up` aplica la migración `003_pgvector.py` sin errores
2. En PostgreSQL: `SELECT * FROM pg_extension WHERE extname='vector'` devuelve 1 fila
3. `python scripts/index_docs.py docs/` indexa archivos locales y popula `document_chunks`
4. `python scripts/scrape_genia.py` scrapea genia.coop y lo indexa
5. En la conversación del agente, al mencionar una tecnología → `buscar_documentos` devuelve resultados reales (no el mock actual)
6. `buscar_cv(tecnologia)` devuelve CVs relevantes

---

## 11. Mejora futura: ChromaDB

Si en el futuro pgvector resulta limitado, ChromaDB se puede evaluar para:
- Re-ranking con cross-encoders (mejor precisión semántica)
- Embeddings automáticos (sin tener que generarlos con sentence-transformers)
- API más simple para prototipado

Pero por ahora, pgvector es suficiente y no agrega infraestructura.

---

## 12. Lo que NO incluye este plan

- Google Drive sync automático (el operador baja los archivos manualmente y corre el script)
- Celery / Redis (no hay tareas periódicas relacionadas)
- Re-ranking con cross-encoders (mejora futura)
- Hybrid search BM25 + vectorial (mejora futura con ChromaDB si hace falta)
