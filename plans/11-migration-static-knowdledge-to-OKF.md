# Plan: de inyección en system prompt a navegación OKF

**Proyecto:** `farox-coop/sales-ai-agent`
**Objetivo:** sacar `GENIA_KNOWLEDGE` del system prompt y reemplazar `buscar_documentos`
(scoring por keywords) por dos tools de navegación estilo Karpathy LLM-wiki / OKF:
`listar_articulos` y `leer_articulo`.

---

## 1. Estado actual

- `src/knowledge/loader.py` carga todos los `.md` de `data/knowledge/` en memoria al
  iniciar (`knowledge_base = KnowledgeBase()`, singleton).
- `src/agent/prompts.py` inyecta el contenido completo de todos los artículos en el
  system prompt vía `knowledge_base.as_context_text()`.
- `src/agent/tools.py` expone `buscar_documentos`, que hace keyword matching +
  scoring manual sobre esos mismos artículos.
- Redundancia: el LLM ya tiene todo el conocimiento en el prompt, y además puede
  buscarlo. Funciona porque el volumen es chico, pero no escala.

## 2. Estado objetivo

- El system prompt **no** incluye el conocimiento de GenIA — solo una instrucción de
  cómo acceder a él.
- El agente navega el conocimiento como un mini-filesystem: primero lista qué hay
  disponible, después abre el/los artículo(s) que necesita.
- Los archivos de `data/knowledge/` migran al formato OKF: Markdown + frontmatter
  YAML, con links entre artículos formando un grafo navegable.
- Se elimina el scoring por keywords (`search()`, `_extract_snippet()`,
  `_extract_tags()`) — no hace falta fallback de búsqueda para este volumen de
  contenido.

---

## 3. Formato OKF para `data/knowledge/*.md`

Cada archivo pasa a tener frontmatter YAML al inicio. Campo obligatorio: `type`.
Opcionales recomendados: `title`, `description`, `tags`.

```markdown
---
type: concept
title: Casos de éxito
description: Resumen de proyectos de IA implementados por GenIA con resultados medibles
tags: [casos-de-exito, resultados, clientes]
---

# Casos de éxito

...contenido existente...

Ver también: [[stack-tecnologico]], [[industrias]]
```

- Los links `[[slug]]` (o `[texto](slug.md)`, según se prefiera) arman el grafo entre
  artículos. El agente los sigue si necesita profundizar en un tema relacionado.
- No hace falta reescribir el contenido, solo agregar el frontmatter y, donde tenga
  sentido, cross-links entre archivos relacionados (ej. `industrias.md` →
  `casos-de-exito.md`).

Referencia de spec: `GoogleCloudPlatform/knowledge-catalog/okf/SPEC.md`.

---

## 4. Cambios en `src/knowledge/loader.py`

Se agrega parseo de frontmatter (con `python-frontmatter` o un regex simple) y se
mantiene `get_full_article`. Se elimina todo lo relacionado a scoring:

```python
import frontmatter  # pip install python-frontmatter
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class KnowledgeArticle:
    slug: str
    title: str
    description: str
    tags: list[str]
    content: str  # cuerpo sin frontmatter


class KnowledgeBase:
    def __init__(self, knowledge_dir: str = "data/knowledge"):
        self.articles: list[KnowledgeArticle] = []
        self._load(knowledge_dir)

    def _load(self, knowledge_dir: str) -> None:
        for filepath in sorted(Path(knowledge_dir).glob("*.md")):
            post = frontmatter.load(filepath)
            self.articles.append(
                KnowledgeArticle(
                    slug=filepath.stem,
                    title=post.get("title", filepath.stem.replace("-", " ").title()),
                    description=post.get("description", ""),
                    tags=post.get("tags", []),
                    content=post.content,
                )
            )

    def list_articles(self) -> list[dict]:
        """Índice liviano: slug, título, descripción, tags. Para listar_articulos."""
        return [
            {"slug": a.slug, "title": a.title, "description": a.description, "tags": a.tags}
            for a in self.articles
        ]

    def get_full_article(self, slug: str) -> str | None:
        for article in self.articles:
            if article.slug == slug:
                return article.content
        return None


knowledge_base = KnowledgeBase()
```

Se eliminan: `search()`, `_extract_tags()`, `_extract_snippet()`, `as_context_text()`.

---

## 5. Cambios en `src/agent/tools.py`

Reemplaza `buscar_documentos` por dos tools:

```python
@tool
async def listar_articulos() -> str:
    """Lista los artículos disponibles en la base de conocimiento de GenIA, con
    título, descripción y tags. Usala primero para orientarte antes de leer el
    contenido completo de un artículo específico."""
    articles = knowledge_base.list_articles()
    lines = [
        f"- {a['slug']}: {a['title']} — {a['description']} [{', '.join(a['tags'])}]"
        for a in articles
    ]
    return "\n".join(lines)


@tool
async def leer_articulo(slug: str) -> str:
    """Devuelve el contenido completo de un artículo de la base de conocimiento de
    GenIA, identificado por su slug (obtenido con listar_articulos). El artículo
    puede contener links a otros artículos relacionados — seguilos si necesitás
    más contexto.

    Args:
        slug: identificador del artículo, ej. 'casos-de-exito'.
    """
    content = knowledge_base.get_full_article(slug.strip())
    if not content:
        return f"No existe un artículo con slug '{slug}'. Usá listar_articulos para ver los disponibles."
    return content
```

Se elimina `buscar_documentos` de `tools.py`, y de `ALL_TOOLS`:

```python
ALL_TOOLS = [
    registrar_lead,
    contador_preguntas,
    listar_articulos,
    leer_articulo,
    buscar_cv,
    generar_resumen,
]
```

`buscar_cv` no se toca — no depende de `KnowledgeBase`.

---

## 6. Cambios en `src/agent/prompts.py`

Se saca `GENIA_KNOWLEDGE` del f-string y se reemplaza por una instrucción de uso de
las tools:

```python
SYSTEM_PROMPT = """...

## Conocimiento sobre GenIA

No tenés el conocimiento de GenIA precargado. Cuando el lead pregunte sobre
GenIA, sus servicios, productos, tecnologías o experiencia:

1. Llamá a listar_articulos para ver qué información hay disponible.
2. Llamá a leer_articulo con el slug del artículo relevante.
3. Si el artículo tiene links a otros artículos relacionados, y son relevantes
   para la pregunta, leelos también.

No inventes features que no aparezcan en los artículos. Si no encontrás
información sobre algo, decilo con honestidad y ofrecé derivar la consulta al
equipo comercial.

...
"""
```

Se elimina el `import` de `knowledge_base` en `prompts.py` si ya no se usa ahí.

---

## 7. Migración de contenido existente

1. Agregar frontmatter a los `.md` actuales (`casos-de-exito.md`, `genia.md`,
   `industrias.md`, etc.) — manual, son pocos archivos.
2. Agregar cross-links entre artículos relacionados donde tenga sentido
   (ej. `industrias.md` menciona un caso → link a `casos-de-exito.md`).
3. Actualizar `make scrape-genia` / `make knowledge-reload` si generan los `.md`
   automáticamente, para que el scraper también genere el frontmatter.

---

## 8. Qué se gana / qué se pierde

**Se gana:**
- System prompt más corto → menos tokens por request, menos costo, menos "ruido"
  para el modelo.
- El agente decide qué leer según la pregunta real del lead, no según un score
  precalculado.
- Más fácil de mantener y de escalar el volumen de contenido sin reescribir lógica
  de scoring.

**Se pierde / a vigilar:**
- Con contenido muy grande, `listar_articulos` devuelve una lista larga y el LLM
  puede elegir mal el slug solo por título — no hay red de seguridad de búsqueda.
  Si esto se vuelve un problema, ahí sí conviene reintroducir un mecanismo de
  búsqueda (keyword o pgvector) como punto de entrada antes de la navegación.
- Cada pregunta sobre GenIA ahora implica al menos 2 tool calls (`listar` +
  `leer`) en vez de tener la respuesta ya en contexto — más latencia por turno,
  aceptable para este volumen de tráfico.

---

## 9. Checklist de implementación

- [ ] Agregar `python-frontmatter` a `pyproject.toml`
- [ ] Migrar los `.md` de `data/knowledge/` con frontmatter + cross-links
- [ ] Reescribir `src/knowledge/loader.py` (sin scoring)
- [ ] Reemplazar `buscar_documentos` por `listar_articulos` + `leer_articulo` en `tools.py`
- [ ] Actualizar `ALL_TOOLS`
- [ ] Sacar `GENIA_KNOWLEDGE` de `prompts.py`, ajustar instrucciones del system prompt
- [ ] Probar conversación completa: preguntas sobre GenIA deben disparar las tools
      correctamente y no alucinar contenido
- [ ] Actualizar `make knowledge-reload` si aplica
