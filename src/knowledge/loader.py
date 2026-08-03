"""Carga y navegación de la base de conocimiento de GenIA en formato OKF.

Cada archivo .md en data/knowledge/ tiene frontmatter YAML con type, title,
description y tags. Los artículos pueden linkearse entre sí con [[slug]].

Sinopsis:
    >>> from src.knowledge.loader import knowledge_base
    >>> articles = knowledge_base.list_articles()
    >>> content = knowledge_base.get_full_article("servicios-ia")
"""

import yaml
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class KnowledgeArticle:
    slug: str
    title: str
    description: str
    tags: list[str]
    content: str


class KnowledgeBase:
    """Base de conocimiento en memoria con navegación estilo OKF.

    Carga todos los archivos .md con frontmatter YAML al instanciarse.
    Expone un índice liviano (list_articles) y acceso completo por slug
    (get_full_article). Sin scoring: el LLM navega por título y descripción.
    """

    def __init__(self, knowledge_dir: str = "data/knowledge"):
        self.articles: list[KnowledgeArticle] = []
        self._load(knowledge_dir)

    def _parse_frontmatter(self, text: str) -> tuple[dict, str]:
        """Extrae frontmatter YAML y contenido del markdown."""
        if not text.startswith("---\n"):
            return {}, text

        parts = text.split("---\n", 2)
        if len(parts) < 3:
            return {}, text

        meta = yaml.safe_load(parts[1]) or {}
        content = parts[2].strip()
        return meta, content

    def _load(self, knowledge_dir: str) -> None:
        dirpath = Path(knowledge_dir)
        if not dirpath.exists():
            return

        for filepath in sorted(dirpath.glob("*.md")):
            raw = filepath.read_text(encoding="utf-8")
            meta, content = self._parse_frontmatter(raw)
            slug = filepath.stem

            self.articles.append(
                KnowledgeArticle(
                    slug=slug,
                    title=meta.get("title", slug.replace("-", " ").title()),
                    description=meta.get("description", ""),
                    tags=meta.get("tags", []),
                    content=content,
                )
            )

    def list_articles(self) -> list[dict]:
        """Índice liviano: slug, título, descripción, tags."""
        return [
            {
                "slug": a.slug,
                "title": a.title,
                "description": a.description,
                "tags": a.tags,
            }
            for a in self.articles
        ]

    def get_full_article(self, slug: str) -> str | None:
        """Devuelve el contenido completo de un artículo por slug."""
        for article in self.articles:
            if article.slug == slug:
                return article.content
        return None

    @property
    def total_articles(self) -> int:
        return len(self.articles)

    @property
    def total_chars(self) -> int:
        return sum(len(a.content) for a in self.articles)


knowledge_base = KnowledgeBase()
