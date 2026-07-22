# Plan 9 — Reemplazo de RAG por conocimiento estático + scraping de genia.coop

**Fecha:** 2026-07-22
**Depende de:** Plan 7 (pgvector-rag) — lo reemplaza
**Origen:** Confirmación del seller: no existen documentos técnicos, CVs ni presupuestos para indexar como base de conocimiento.

---

## 1. Diagnóstico: qué cambió

### 1.1 Lo que se asumía hasta ahora

Los planes 1, 2, 3, 7, 8 y el plan maestro (`lead-magnet-conversational-agent.md`) asumían la
existencia de una base de conocimiento interna de Farox compuesta por:

- **Propuestas comerciales** (PDFs en Google Drive)
- **CVs de ingenieros** (perfiles profesionales para matchear con necesidades del lead)
- **Presupuestos de referencia** (documentos financieros para estimar costos)
- **Documentos técnicos** (arquitecturas, specs, casos de estudio)

Esto motivó todo el diseño de RAG con pgvector: extensión `vector`, tabla `document_chunks`,
modelo de embeddings `sentence-transformers`, pipeline de chunking, búsqueda semántica, etc.

### 1.2 La realidad

Después de hablar con el seller, se confirmó que **no existen esos documentos**. El único
contenido disponible que describe lo que Farox hace como empresa es:

- **El sitio web https://genia.coop** — expone servicios, productos, capacidades y casos de
  éxito alrededor de IA.

No hay PDFs internos, no hay CVs estructurados, no hay presupuestos de referencia. Esto
cambia completamente la ecuación: **el volumen de contenido no justifica una pipeline de RAG**.

---

## 2. Análisis de opciones

### Opción A: RAG solo con genia.coop

Scrapear genia.coop → chunkear → embeddear → pgvector → búsqueda semántica en runtime.

| Criterio | Evaluación |
|----------|-----------|
| Volumen de contenido | ~10-20 páginas web, ~50-100KB de texto |
| Complejidad | pgvector + sentence-transformers (~120MB modelo) + chunker + scraper + retriever |
| Mantenibilidad | Cada cambio en el sitio requiere re-scrapear y re-indexar |
| Latencia | Embedding de query + búsqueda vectorial en cada tool call |
| Escalabilidad | Sobredimensionado para 100KB de texto |

### Opción B: Archivos .md estáticos + búsqueda simple

Scrapear genia.coop una vez → generar archivos `.md` → cargarlos al iniciar el agente →
búsqueda por keyword o inclusión directa en el system prompt.

| Criterio | Evaluación |
|----------|-----------|
| Volumen de contenido | ~10-20 páginas → 5-10KB de texto relevante |
| Complejidad | Cero infraestructura nueva |
| Mantenibilidad | Editar los .md a mano cuando el sitio cambie |
| Latencia | Instantáneo (todo en memoria) |
| Escalabilidad | Si el contenido crece mucho (>200KB), el system prompt se satura |

### Opción C: SQL full-text search (PostgreSQL `tsvector`)

Scrapear genia.coop → guardar en tabla `documentos` con índice `tsvector` → búsqueda
full-text en runtime.

| Criterio | Evaluación |
|----------|-----------|
| Volumen de contenido | ~10-20 páginas |
| Complejidad | Baja: PostgreSQL ya tiene `tsvector` nativo, sin extensiones extra |
| Mantenibilidad | Misma que Opción A |
| Latencia | <5ms (búsqueda SQL simple) |
| Escalabilidad | Mejor que .md, peor que RAG para búsqueda semántica real |

### Opción D: Híbrida — .md ahora, RAG como upgrade opcional

Arrancar con .md cargados en memoria. Si en el futuro aparecen documentos reales, el proyecto
ya tiene el diseño de RAG documentado (Plan 7) y se puede implementar sin cambiar la interfaz
de las tools.

| Criterio | Evaluación |
|----------|-----------|
| Pragmatismo | ALTO — solo construimos lo que necesitamos hoy |
| Deuda técnica | BAJA — la interfaz de tools se mantiene, cambia el backend |
| Flexibilidad | ALTA — el día que haya docs reales, se implementa pgvector |

---

## 3. Recomendación: Opción D (híbrida)

### 3.1 Por qué no RAG ahora

1. **Volumen insignificante.** ~50-100KB de texto no necesita búsqueda semántica vectorial.
   Cargarlo en memoria o en el system prompt es más rápido y más simple.

2. **Sobrecarga cognitiva y de infraestructura.** pgvector requiere:
   - Extensión de PostgreSQL (`CREATE EXTENSION vector`)
   - Modelo de embeddings (~120MB descargado, cargado en RAM)
   - Pipeline de chunking + indexación
   - Scripts de scraping y re-indexación
   - Dependencias: `pgvector`, `sentence-transformers`, `beautifulsoup4`, `lxml`, `pypdf`
   - Todo esto para buscar en el equivalente a 20 páginas de texto.

3. **Sin fuente de documentos reales.** Los documentos que justificaban RAG (propuestas, CVs,
   presupuestos) no existen. El scraping de genia.coop era un complemento, no la fuente
   principal.

4. **YAGNI.** Si nunca llegan documentos reales, pgvector queda como dead code para siempre.
   Si llegan, se implementa en ese momento.

### 3.2 Qué hacemos en su lugar

1. **Scrapear genia.coop una vez** y generar archivos `.md` estructurados con el contenido
   relevante de cada sección del sitio.

2. **Cargar el contenido al iniciar el agente** como un objeto `KnowledgeBase` en memoria.

3. **Reemplazar `buscar_documentos`** por una búsqueda simple sobre ese conocimiento:
   keyword matching + relevancia básica (sin embeddings).

4. **Eliminar `buscar_cv`** — no hay CVs ni perfiles para buscar.

5. **Simplificar el modelo de datos**: la tabla `documentos` actual (sin usar) se puede
   mantener vacía o directamente eliminar. La tabla `document_chunks` del Plan 7 nunca se crea.

---

## 4. Diseño propuesto

### 4.1 Estructura de archivos

```
data/knowledge/                    # Conocimiento estático sobre Farox
├── farox.md                       # Quiénes somos, misión, servicios principales
├── servicios-ia.md                # Servicios de IA: consultoría, desarrollo, entrenamiento
├── productos.md                   # Productos de IA (ej. agentes, automatización)
├── casos-de-exito.md              # Casos de éxito / portfolio
├── industrias.md                  # Industrias con las que trabajan
├── tecnologias.md                 # Stack tecnológico que manejan
└── proceso-de-trabajo.md          # Cómo trabajan (metodología, entregables)

src/knowledge/
├── __init__.py
└── loader.py                      # Carga los .md en memoria, búsqueda simple
```

### 4.2 `src/knowledge/loader.py`

```python
"""Carga y búsqueda simple sobre la base de conocimiento estática de Farox.

El conocimiento viene de archivos .md generados a partir del scraping de
genia.coop. Se cargan en memoria al iniciar el agente y se buscan por
keyword matching + scoring básico de relevancia.
"""

import re
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class KnowledgeArticle:
    """Un artículo de conocimiento (un archivo .md)."""
    slug: str           # ej. "servicios-ia"
    title: str          # primer heading del archivo
    content: str        # texto completo
    tags: list[str]     # keywords extraídas para búsqueda


class KnowledgeBase:
    """Base de conocimiento en memoria con búsqueda simple."""

    def __init__(self, knowledge_dir: str = "data/knowledge"):
        self.articles: list[KnowledgeArticle] = []
        self._load(knowledge_dir)

    def _load(self, knowledge_dir: str) -> None:
        """Carga todos los archivos .md del directorio."""
        dirpath = Path(knowledge_dir)
        if not dirpath.exists():
            return

        for filepath in sorted(dirpath.glob("*.md")):
            text = filepath.read_text(encoding="utf-8")
            slug = filepath.stem

            # Extraer título (primer heading)
            title_match = re.search(r"^# (.+)$", text, re.MULTILINE)
            title = title_match.group(1) if title_match else slug.replace("-", " ").title()

            # Extraer tags (del frontmatter o de headings)
            tags = self._extract_tags(text)

            self.articles.append(KnowledgeArticle(
                slug=slug,
                title=title,
                content=text,
                tags=tags,
            ))

    def _extract_tags(self, text: str) -> list[str]:
        """Extrae keywords relevantes de headings y palabras clave."""
        # Simple: headings h2/h3 y palabras en negrita
        headings = re.findall(r"^#{2,3}\s+(.+)$", text, re.MULTILINE)
        bold = re.findall(r"\*\*(.+?)\*\*", text)
        all_keywords = [h.lower() for h in headings + bold]
        return list(set(all_keywords))

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """Búsqueda simple por keyword matching.

        Scoring:
        - +3 puntos por match exacto de palabra clave
        - +2 puntos por match en tags/headings
        - +1 punto por match en contenido
        - Penalización por longitud para favorecer artículos más específicos
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())
        results = []

        for article in self.articles:
            score = 0

            # Match en título
            if query_lower in article.title.lower():
                score += 5

            # Match en tags
            tag_matches = sum(
                1 for tag in article.tags
                if query_lower in tag or any(w in tag for w in query_words)
            )
            score += tag_matches * 2

            # Match en contenido
            content_lower = article.content.lower()
            word_matches = sum(1 for w in query_words if w in content_lower)
            score += word_matches

            if score > 0:
                # Extraer snippet relevante (~200 chars alrededor del match)
                snippet = self._extract_snippet(article.content, query_words)

                results.append({
                    "slug": article.slug,
                    "title": article.title,
                    "score": score,
                    "snippet": snippet,
                })

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]

    def _extract_snippet(self, content: str, query_words: set[str]) -> str:
        """Extrae un fragmento relevante de ~200 chars."""
        content_clean = re.sub(r"^#.*$", "", content, flags=re.MULTILINE)  # quitar headings
        content_clean = re.sub(r"\*\*|\*", "", content_clean)  # quitar bold/italic
        content_clean = content_clean.strip()

        # Buscar la primera ocurrencia de alguna query word
        idx = -1
        for w in query_words:
            pos = content_clean.lower().find(w)
            if pos != -1 and (idx == -1 or pos < idx):
                idx = pos

        if idx == -1:
            # Sin match exacto, devolver primeras 200 chars
            return content_clean[:200] + "..."

        start = max(0, idx - 100)
        end = min(len(content_clean), idx + 100)
        snippet = content_clean[start:end].strip()
        if start > 0:
            snippet = "..." + snippet
        if end < len(content_clean):
            snippet = snippet + "..."

        return snippet

    def get_full_article(self, slug: str) -> str | None:
        """Devuelve el contenido completo de un artículo por slug."""
        for article in self.articles:
            if article.slug == slug:
                return article.content
        return None

    def as_context_text(self) -> str:
        """Devuelve todo el conocimiento como texto para incluir en el system prompt.

        Útil si el volumen es chico y queremos que el LLM tenga acceso completo
        sin necesidad de tool calls.
        """
        parts = []
        for article in self.articles:
            parts.append(f"## {article.title}\n\n{article.content}")
        return "\n\n---\n\n".join(parts)

    @property
    def total_articles(self) -> int:
        return len(self.articles)

    @property
    def total_chars(self) -> int:
        return sum(len(a.content) for a in self.articles)


# Singleton cargado al iniciar
knowledge_base = KnowledgeBase()
```

### 4.3 Integración con el system prompt

Dos opciones no excluyentes:

**Opción A: Como parte del system prompt (recomendado para arrancar)**

Si el contenido total de genia.coop es < 15KB (~3000 tokens), se puede incluir completo
en el system prompt. El agente tiene acceso a TODO el conocimiento sin tool calls.

```python
# En prompts.py
from src.knowledge.loader import knowledge_base

FAROX_KNOWLEDGE = knowledge_base.as_context_text()

SYSTEM_PROMPT = f"""Eres un consultor de IA de Farox...

## Conocimiento sobre Farox

A continuación tenés información actualizada sobre los servicios, productos y
capacidades de Farox. Usala para responder preguntas del lead con precisión.

{FAROX_KNOWLEDGE}

## Herramientas disponibles
...
"""
```

**Ventaja:** El agente siempre tiene el contexto de Farox sin necesidad de tool calls.
El lead pregunta "¿tienen experiencia en retail?" y el agente ya sabe la respuesta.

**Riesgo:** Si el contenido crece mucho, empieza a comerse tokens del system prompt y
deja menos espacio para el historial de la conversación. Para el volumen actual (~10-20
páginas), no es un problema.

**Opción B: Solo por tool call (más escalable)**

El system prompt solo menciona que `buscar_documentos` existe y puede buscar info de
Farox. El conocimiento se carga en `KnowledgeBase` y se busca on-demand.

**Ventaja:** Escala mejor si el contenido crece. El agente solo "ve" lo relevante a
la pregunta.

**Desventaja:** Agrega un tool call (y por lo tanto un round-trip al LLM) cada vez que
el lead pregunta algo sobre Farox. Para contenido chico, es overhead innecesario.

**Recomendación:** **Opción A ahora, Opción B cuando el contenido supere ~20KB (~5000 tokens).**
Incluso se pueden combinar: incluir un resumen de servicios en el prompt, y usar la tool
para búsqueda detallada.

### 4.4 Cambio en tool_handlers.py

`handle_buscar_documentos` y `handle_buscar_cv` se reescriben:

```python
# En tool_handlers.py
from src.knowledge.loader import knowledge_base

async def handle_buscar_documentos(
    db: AsyncSession, lead_id: uuid.UUID, args: dict
) -> dict:
    """Busca en la base de conocimiento estática de Farox."""
    query = args.get("query", "")

    if not query:
        return {"query": "", "resultados": [], "total": 0}

    results = knowledge_base.search(query, top_k=3)

    if not results:
        return {
            "query": query,
            "resultados": [],
            "total": 0,
            "nota": "No se encontró información relevante en la base de conocimiento.",
        }

    return {
        "query": query,
        "resultados": [
            {
                "titulo": r["title"],
                "relevancia": r["score"],
                "fragmento": r["snippet"],
            }
            for r in results
        ],
        "total": len(results),
    }


async def handle_buscar_cv(
    db: AsyncSession, lead_id: uuid.UUID, args: dict
) -> dict:
    """Deprecada: Farox no tiene CVs indexados."""
    return {
        "tecnologia": args.get("tecnologia", ""),
        "resultados": [],
        "total": 0,
        "nota": (
            "Farox no mantiene una base de CVs indexados. Si el lead pregunta "
            "por perfiles específicos, derivá la consulta al equipo comercial "
            "para que evalúen disponibilidad de recursos."
        ),
    }
```

### 4.5 Cambios en tools.py

La definición de `buscar_documentos` se actualiza para reflejar la nueva realidad:

```python
{
    "type": "function",
    "function": {
        "name": "buscar_documentos",
        "description": (
            "Busca información sobre Farox en la base de conocimiento: servicios, "
            "productos, casos de éxito, industrias, tecnologías y metodología de trabajo. "
            "Usala cuando el lead pregunta sobre las capacidades de Farox, experiencia "
            "en una industria, casos de éxito o stack tecnológico."
        ),
        ...
    },
},
```

`buscar_cv` se puede mantener con descripción actualizada que indique que es informativa
(no busca CVs reales) o directamente eliminar. **Recomendación: mantener pero con
descripción honesta** — si el lead pregunta por perfiles, el agente puede usar la tool,
recibir la nota de que no hay CVs, y responder apropiadamente.

### 4.6 Scraping de genia.coop

Se crea `scripts/scrape_genia_to_md.py` — similar al del Plan 7 pero en vez de indexar en
pgvector, genera archivos `.md` en `data/knowledge/`.

```python
"""Scrapea genia.coop y genera archivos .md en data/knowledge/.

Uso único (no es pipeline recurrente):
    python scripts/scrape_genia_to_md.py

Genera un .md por cada sección relevante del sitio.
Los archivos se editan manualmente para pulir, corregir y
agregar información que el scraping no capturó bien.
"""

URLS = [
    ("index", "https://genia.coop"),
    ("servicios-ia", "https://genia.coop/servicios"),
    ("productos", "https://genia.coop/productos"),
    ("casos-de-exito", "https://genia.coop/casos-de-exito"),
    # ... más URLs según la estructura real del sitio
]
```

**Importante:** El scraping es **punto de partida**, no fuente definitiva. Los .md generados
se revisan, editan y mantienen manualmente. El script de scraping corre una vez para generar
el borrador inicial y quizás una vez cada 3-6 meses para actualizar.

---

## 5. Lo que se elimina del proyecto

| Ítem | Motivo |
|------|--------|
| Plan 7 completo (`07-pgvector-rag.md`) | Reemplazado por este plan |
| `src/rag/` (directorio entero) | Sin RAG, no hay chunker, embedder, indexer, retriever |
| `scripts/index_docs.py` | Sin documentos para indexar |
| `scripts/scrape_genia.py` | Reemplazado por `scrape_genia_to_md.py` |
| `scripts/rebuild_index.py` | Sin índice vectorial que reconstruir |
| Tabla `document_chunks` (Plan 7) | Nunca se crea |
| Extensión `vector` de PostgreSQL | No se instala |
| Dependencias: `pgvector`, `sentence-transformers`, `pypdf` | Sin RAG, sin PDFs, sin embeddings |
| Dependencia: `beautifulsoup4` + `lxml` | El scraping ahora es puntual, puede ser un script con `httpx` + `bs4` como dependencia de dev |
| Campo `documentos.chunks_count` | Sin chunks, no tiene sentido |
| Campo `documentos.fuente` (Plan 7) | Ya no aplica |
| Tool `buscar_cv` | Pasa a ser un stub que informa que no hay CVs (o se elimina) |

---

## 6. Lo que se mantiene o se crea

| Ítem | Acción |
|------|--------|
| `data/knowledge/*.md` | **Nuevo**. Archivos de conocimiento sobre Farox |
| `src/knowledge/__init__.py` | **Nuevo** |
| `src/knowledge/loader.py` | **Nuevo**. Carga y búsqueda simple en memoria |
| `scripts/scrape_genia_to_md.py` | **Nuevo**. Scraping → .md (una vez) |
| `src/agent/tools.py` | Actualizar descripciones de `buscar_documentos` y `buscar_cv` |
| `src/agent/tool_handlers.py` | Reemplazar stubs por `KnowledgeBase.search()` |
| `src/agent/prompts.py` | Agregar sección con conocimiento de Farox (opcional: inline en system prompt) |
| Tabla `documentos` en DB | Se puede mantener vacía (no molesta) o dropear en migración futura |
| `Makefile` | Agregar target `scrape-genia` y `knowledge-reload` |

---

## 7. Migración de DB

Si se decide limpiar la tabla `documentos` (está vacía, nunca tuvo datos reales):

```python
# Nueva migración 003_cleanup_rag.py
def upgrade():
    # La tabla documentos se creó en 002_plan2.py para el RAG.
    # Sin documentos reales que indexar, se puede dropear o mantener vacía.
    # Por ahora la dejamos — no ocupa espacio y no molesta.
    # Si en el futuro se implementa RAG con documentos reales, se reutiliza.
    pass
```

**Decisión: no dropear la tabla.** Está vacía, no consume recursos, y si en el futuro
aparecen documentos reales, ya existe. Es más limpio dejarla que crear/dropear/crear.

---

## 8. Plan de implementación

### Fase 9A — Scraping inicial (1 sesión)

1. Navegar genia.coop y mapear todas las páginas/secciones relevantes
2. Crear `scripts/scrape_genia_to_md.py`
3. Ejecutar y generar borradores en `data/knowledge/`
4. Revisar y editar manualmente cada .md para precisión y completitud
5. Validar con el seller que la info es correcta

### Fase 9B — Cargador de conocimiento (1 sesión)

1. Implementar `src/knowledge/loader.py` con `KnowledgeBase`
2. Probar búsqueda con queries de ejemplo
3. Integrar en `tool_handlers.py` (reemplazar stubs actuales)
4. Actualizar definiciones en `tools.py`

### Fase 9C — Integración en el agente (1 sesión)

1. Decidir si el conocimiento va inline en el system prompt o solo vía tool
2. Actualizar `prompts.py`
3. Probar conversación donde el lead pregunta por servicios de Farox
4. Verificar que las respuestas son precisas y no alucina features inexistentes

### Fase 9D — Limpieza de planes existentes (1 sesión)

Actualizar los planes 1, 2, 3, 7, 8 y el plan maestro para reflejar que:
- RAG con pgvector queda como "mejora futura si aparecen documentos reales"
- `buscar_documentos` usa conocimiento estático en memoria
- `buscar_cv` es un stub informativo

---

## 9. Archivos involucrados en este plan

| Archivo | Acción |
|---------|--------|
| `data/knowledge/*.md` | **Nuevo**. Conocimiento estático de Farox (~7-10 archivos) |
| `src/knowledge/__init__.py` | **Nuevo** |
| `src/knowledge/loader.py` | **Nuevo**. KnowledgeBase con búsqueda simple |
| `scripts/scrape_genia_to_md.py` | **Nuevo**. Scraping one-shot → .md |
| `src/agent/tools.py` | Actualizar descripciones de `buscar_documentos` y `buscar_cv` |
| `src/agent/tool_handlers.py` | `handle_buscar_documentos` → `knowledge_base.search()`. `handle_buscar_cv` → stub honesto |
| `src/agent/prompts.py` | Agregar conocimiento de Farox (inline o referencia) |
| `Makefile` | Agregar `scrape-genia` target |
| `plans/09-rag-replacement-static-knowledge.md` | **Este archivo** |

---

## 10. Mejora futura: RAG con documentos reales

Si en el futuro Farox genera o adquiere documentos que justifiquen una base de conocimiento
semántica (propuestas reales, documentación técnica, papers, CVs de un equipo grande), el
diseño de RAG con pgvector del Plan 7 sigue siendo la arquitectura recomendada. La interfaz
de `buscar_documentos` se diseñó para que el cambio de backend (memoria → pgvector) sea
transparente para el agente.

Condiciones que justificarían volver a evaluar RAG:
- 50+ documentos o 500KB+ de texto
- Necesidad de búsqueda semántica real (no solo keyword matching)
- Documentos en múltiples formatos (PDF, DOCX, MD)
- Conocimiento que cambia frecuentemente y necesita re-indexación

Mientras tanto, KISS.

---

## 11. Verificación

1. `data/knowledge/` contiene .md con información precisa de genia.coop
2. `KnowledgeBase.load()` carga todos los archivos sin errores
3. `KnowledgeBase.search("machine learning")` devuelve resultados relevantes
4. `KnowledgeBase.search("industria retail")` devuelve casos de éxito si existen
5. `handle_buscar_documentos` ya no es un mock — devuelve resultados reales
6. `handle_buscar_cv` devuelve mensaje informativo (sin CVs disponibles)
7. En una conversación de prueba, el agente responde con precisión sobre servicios de Farox
8. El agente no alucina features o servicios que Farox no ofrece
