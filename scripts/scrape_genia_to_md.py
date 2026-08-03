"""
Scrapea contenido de genia.coop y genera archivos .md en data/knowledge/.

genia.coop es una React SPA — el scraping HTML tradicional no funciona
porque todo el contenido está en el JS bundle. Este script extrae el
contenido en español del bundle y genera archivos .md para secciones
nuevas que no tengan un archivo curado existente.

Los archivos existentes (curados manualmente) NO se sobreescriben.
Solo se crean archivos nuevos para contenido no cubierto.

Uso:
    python scripts/scrape_genia_to_md.py /tmp/genia_bundle.js
"""

import json
import os
import re
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

KNOWLEDGE_DIR = Path("data/knowledge")

# Mapeo de secciones del sitio → archivo .md a crear (solo si no existe ya)
SECTION_TO_NEW_FILE = {
    "genbase": "genbase.md",
    "genway": "genway.md",
    "howItWorks": "inferencia.md",
}

FILE_CONFIG = {
    "genbase.md": {
        "type": "concept",
        "title": "GenBase — Infraestructura de IA para la Innovación Científica",
        "description": "GenBase convierte el conocimiento científico en una plataforma de IA colaborativa: RAG empresarial, Data Lakes e IA predictiva.",
        "tags": ["genbase", "rag", "data-lake", "ia-predictiva", "conocimiento", "infraestructura"],
        "related": ["genway", "inferencia", "productos", "servicios-ia", "tecnologias"],
    },
    "genway.md": {
        "type": "concept",
        "title": "Genway — Centro de Mando de Gobernanza de IA",
        "description": "Genway es la capa de gobierno de IA que da visibilidad total y control sobre cómo, quién y con qué modelos se trabaja.",
        "tags": ["genway", "gobierno", "control", "privacidad", "ruteo"],
        "related": ["genbase", "inferencia", "productos", "servicios-ia", "tecnologias"],
    },
    "inferencia.md": {
        "type": "concept",
        "title": "InferencIA — Arquitectura Abierta de IA",
        "description": "InferencIA es la arquitectura abierta de GenIA que unifica modelos, agentes y conocimiento en un stack self-hosted.",
        "tags": ["inferencia", "stack", "self-hosted", "modelos", "agentes"],
        "related": ["genbase", "genway", "productos", "servicios-ia", "tecnologias"],
    },
}

DEFAULT_FRONTMATTER = {
    "type": "concept",
    "tags": ["genia"],
}


def extract_es_block(content: str) -> str:
    """Encuentra el bloque de contenido en español dentro del bundle JS."""
    es_marker = ',label:"ES"},'
    en_marker = ',label:"EN"},'

    es_idx = content.find(es_marker)
    if es_idx == -1:
        raise ValueError("No se encontró el bloque de contenido en español")

    start = es_idx + len(es_marker)
    en_idx = content.find(en_marker, start)
    if en_idx == -1:
        raise ValueError("No se encontró el bloque de contenido en inglés")

    return content[start:en_idx]


def find_section_content(es_block: str, section_key: str) -> str:
    """Extrae el contenido de una sección del bloque JS rastreando llaves."""
    pattern = rf'{section_key}:\{{'
    match = re.search(pattern, es_block)
    if not match:
        return ""

    rest = es_block[match.end() - 1:]
    depth = 0
    in_string = False
    escape_next = False

    for i, c in enumerate(rest):
        if escape_next:
            escape_next = False
            continue
        if c == '\\':
            escape_next = True
            continue
        if c == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return rest[:i + 1]

    return ""


def extract_strings_from_section(section_content: str) -> list[str]:
    """Extrae strings significativos de una sección."""
    pattern = re.compile(r'"([^"]{10,400})"', re.DOTALL)
    matches = pattern.findall(section_content)

    code_patterns = [
        "http", "function", "const ", "return", "import", "export",
        ".js", ".css", "react", "class", "div", "span", "auto", "rgb",
        "px", "src:", "type:", "path:", "module", "require", "props",
        "key:", "onClick", "onChange", "setState", "useState",
        "useEffect", "useRef", "useMemo", "useCallback", "className",
        "children", "fragment", "jsxs", "jsxDEV", "__",
        "dispatch", "reducer", "action", "payload",
        "current", "pending", "resolved", "rejected",
        "fulfilled", "undefined", "null",
        "style", "display", "position", "padding", "margin",
        "width", "height", "color", "background", "font",
        "border", "flex", "grid", "align", "justify",
        "transform", "translate", "rotate", "scale",
        "transition", "animation", "opacity",
        "linear", "ease", "ease-in", "ease-out",
        "object-fit", "object-position",
        "z-index", "overflow", "cursor",
        "pointer-events", "user-select",
        "box-shadow", "text-align", "white-space",
        "text-transform", "text-decoration",
        "font-size", "font-weight", "line-height",
        "letter-spacing", "word-break",
        "data-", "aria-", "role=",
        "M", "C", "L", "Q", "A", "H", "V", "Z",
        "hsl(", "hsla(", "rgba(", "var(",
    ]

    def is_ui_text(s: str) -> bool:
        s_lower = s.lower()
        for pat in code_patterns:
            if pat in s_lower:
                return False
        special_ratio = sum(
            1 for c in s if c in '{}[]()<>;=+|&^%$#@!`~\\'
        ) / max(len(s), 1)
        if special_ratio > 0.1:
            return False
        if re.match(r'^[0-9.,\s%pxremvhvw]+$', s):
            return False
        return len(s.split()) >= 3

    def clean_string(s: str) -> str:
        s = s.replace("\\n", "\n").replace("\\t", "    ")
        s = s.replace('\\"', '"').replace("\\\\", "\\")
        s = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), s)
        return s.strip()

    result = []
    for m in matches:
        clean = clean_string(m.strip())
        if is_ui_text(clean):
            result.append(clean)

    seen = set()
    unique = []
    for r in result:
        if r not in seen:
            seen.add(r)
            unique.append(r)

    return unique


def build_markdown(title: str, strings: list[str], frontmatter: dict, related: list[str] | None = None) -> str:
    """Construye el contenido markdown a partir de strings extraídos."""
    lines = []
    lines.append("---")
    for key in ["type", "title", "description", "tags"]:
        if key in frontmatter:
            val = frontmatter[key]
            if isinstance(val, list):
                lines.append(f"{key}: [{', '.join(val)}]")
            else:
                lines.append(f"{key}: {json.dumps(val, ensure_ascii=False)}")
    lines.append(f"scraped: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")

    for s in strings:
        if s and len(s) > 5:
            lines.append(s)
            lines.append("")

    if related:
        links = ", ".join(f"[[{r}]]" for r in related)
        lines.append(f"Ver también: {links}")
        lines.append("")

    return "\n".join(lines)


def get_all_section_keys(es_block: str) -> list[str]:
    """Encuentra todas las claves de secciones top-level en el bloque ES."""
    pattern = re.compile(r'([a-zA-Z]+):\{')
    matches = pattern.findall(es_block)
    seen = OrderedDict()
    for m in matches:
        seen[m] = True
    return list(seen.keys())


def main():
    if len(sys.argv) < 2:
        filepath = "/tmp/genia_bundle.js"
    else:
        filepath = sys.argv[1]

    if not os.path.exists(filepath):
        print(f"ERROR: Archivo no encontrado: {filepath}")
        sys.exit(1)

    with open(filepath, "r") as f:
        content = f.read()

    print("Extrayendo bloque de contenido en español...")
    try:
        es_block = extract_es_block(content)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(f"Bloque ES: {len(es_block)} chars")

    all_keys = get_all_section_keys(es_block)
    print(f"Secciones top-level: {all_keys}")

    # --- Extraer contenido por sección ---
    target_sections = {
        "genbase": ["hub", "datalake", "predictive", "rag", "diagram"],
        "genway": [],
        "howItWorks": [],
    }

    sections_data = {}
    for section_key, subs in target_sections.items():
        section_content = find_section_content(es_block, section_key)
        if not section_content:
            print(f"  [SKIP] {section_key}: no encontrada")
            continue

        strings = extract_strings_from_section(section_content)
        for sub in subs:
            sub_content = find_section_content(es_block, sub)
            if sub_content:
                strings.extend(extract_strings_from_section(sub_content))

        if strings:
            sections_data[section_key] = strings
            print(f"  [OK] {section_key}: {len(strings)} strings")
        else:
            print(f"  [EMPTY] {section_key}: sin strings significativos")

    # --- Generar .md solo para archivos que NO existen ---
    created = []
    skipped = []

    for section_key, strings in sections_data.items():
        filename = SECTION_TO_NEW_FILE.get(section_key)
        if not filename:
            continue

        filepath_md = KNOWLEDGE_DIR / filename
        config = FILE_CONFIG.get(filename, DEFAULT_FRONTMATTER.copy())
        title = config.get("title", section_key)
        related = config.get("related", [])

        frontmatter_fields = {k: config[k] for k in ["type", "title", "description", "tags"] if k in config}

        if filepath_md.exists():
            skipped.append(filename)
            print(f"\n  [SKIP] {filename}: ya existe (curado manualmente)")
            print(f"  Contenido scrapeado ({len(strings)} strings) disponible si querés actualizarlo manualmente.")
        else:
            md_content = build_markdown(title, strings, frontmatter_fields, related)
            filepath_md.write_text(md_content, encoding="utf-8")
            created.append(filename)
            print(f"\n  [CREADO] {filename}: {len(strings)} strings")

    # --- Reporte ---
    print(f"\n{'='*60}")
    if created:
        print(f"Creados: {', '.join(created)}")
    if skipped:
        print(f"No modificados (ya existen): {', '.join(skipped)}")
    if not created and not skipped:
        print("No se generó ningún archivo nuevo.")
    print(f"\nEjecutá 'make knowledge-reload' para recargar la base de conocimiento.")


if __name__ == "__main__":
    main()
