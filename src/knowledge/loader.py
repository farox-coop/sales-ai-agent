"""Carga y búsqueda simple sobre la base de conocimiento estática de GenIA.

El conocimiento viene de archivos .md generados a partir del scraping de
genia.coop. Se cargan en memoria al iniciar el agente y se buscan por
keyword matching + scoring básico de relevancia.

Sinopsis:
    >>> from src.knowledge.loader import knowledge_base
    >>> results = knowledge_base.search("machine learning")
    >>> text = knowledge_base.as_context_text()  # para incluir en system prompt
"""

import re
from pathlib import Path
from dataclasses import dataclass


@dataclass
class KnowledgeArticle:
    """Un artículo de conocimiento (un archivo .md)."""

    slug: str  # ej. "servicios-ia"
    title: str  # primer heading del archivo
    content: str  # texto completo
    tags: list[str]  # keywords extraídas para búsqueda


class KnowledgeBase:
    """Base de conocimiento en memoria con búsqueda simple.

    Carga todos los archivos .md de un directorio al instanciarse y
    permite búsqueda por keyword matching sin dependencias externas.
    """

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
            title = (
                title_match.group(1)
                if title_match
                else slug.replace("-", " ").title()
            )

            # Extraer tags (de headings y bold)
            tags = self._extract_tags(text)

            self.articles.append(
                KnowledgeArticle(
                    slug=slug,
                    title=title,
                    content=text,
                    tags=tags,
                )
            )

    def _extract_tags(self, text: str) -> list[str]:
        """Extrae keywords relevantes de headings y palabras en negrita."""
        headings = re.findall(r"^#{2,4}\s+(.+)$", text, re.MULTILINE)
        bold = re.findall(r"\*\*(.+?)\*\*", text)
        all_keywords = [h.lower() for h in headings + bold]
        return list(set(all_keywords))

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """Búsqueda simple por keyword matching.

        Scoring:
        - +5 puntos por match en título
        - +3 puntos por match exacto de frase o palabra clave
        - +2 puntos por match en tags/headings
        - +1 punto por match en contenido
        """
        query_lower = query.lower()
        # Filtrar stop words en español y palabras muy cortas
        stop_words = {
            "de", "del", "la", "el", "los", "las", "un", "una", "unos", "unas",
            "en", "con", "por", "para", "sin", "sobre", "entre", "hasta", "desde",
            "y", "o", "a", "e", "ni", "que", "es", "se", "su", "sus",
            "al", "del", "lo", "le", "les", "me", "te", "nos", "os",
            "el", "la", "lo", "los", "las", "les",
        }
        query_words = {w for w in query_lower.split() if w not in stop_words and len(w) > 2}
        if not query_words:
            query_words = set(query_lower.split())  # fallback: usar todas
        results = []

        for article in self.articles:
            score = 0

            # Match en título (boost fuerte para frase exacta o palabras sueltas)
            if query_lower in article.title.lower():
                score += 15
            else:
                # Boost más chico si palabras sueltas del query están en el título
                title_lower = article.title.lower()
                title_word_matches = sum(1 for w in query_words if w in title_lower)
                score += title_word_matches * 7

            # Match exacto de la query completa en contenido
            if query_lower in article.content.lower():
                score += 3

            # Match en tags
            tag_matches = sum(
                1
                for tag in article.tags
                if query_lower in tag or any(w in tag for w in query_words)
            )
            score += tag_matches * 2

            # Match en contenido por palabra (normalizado por largo del doc)
            content_lower = article.content.lower()
            word_matches = sum(1 for w in query_words if w in content_lower)
            doc_len_words = max(len(article.content.split()), 1)

            # Frecuencia acumulada: palabras que aparecen mucho en un doc corto
            # indican que es el tema central del artículo
            frequency_bonus = sum(
                content_lower.count(w) for w in query_words
            )
            score += word_matches * (500 / doc_len_words)
            score += frequency_bonus * (300 / doc_len_words)

            if score > 0:
                snippet = self._extract_snippet(article.content, query_words)

                results.append(
                    {
                        "slug": article.slug,
                        "title": article.title,
                        "score": score,
                        "snippet": snippet,
                    }
                )

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]

    def _extract_snippet(self, content: str, query_words: set[str]) -> str:
        """Extrae un fragmento relevante de ~200 chars."""
        # Limpiar markdown para el snippet
        content_clean = re.sub(
            r"^#.*$", "", content, flags=re.MULTILINE
        )  # quitar headings
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
            snippet = content_clean[:200]
            if len(content_clean) > 200:
                snippet += "..."
            return snippet

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
