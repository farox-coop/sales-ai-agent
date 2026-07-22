"""Scrapea contenido de genia.coop y lo extrae como texto legible.

genia.coop es una React SPA hosteada en GitHub Pages — el scraping HTML
tradicional no funciona porque todo el contenido está en el JS bundle.

Este script extrae el texto del bundle para facilitar la generación de los
archivos .md en data/knowledge/. No es una pipeline recurrente — se corre
una vez para auditar el contenido actual del sitio y actualizar los .md
manualmente si es necesario.

Uso:
    curl -sL https://genia.coop/assets/index-3OEbpqcP.js > /tmp/genia_bundle.js
    python scripts/scrape_genia_to_md.py /tmp/genia_bundle.js

Los archivos .md en data/knowledge/ se mantienen y editan manualmente.
Este script es solo una herramienta de extracción inicial.
"""

import re
import sys


def extract_strings(content: str) -> list[str]:
    """Extract string literals that look like UI text (Spanish content)."""
    # Matches quoted strings
    pattern = re.compile(r'"([^"]{20,300})"', re.DOTALL)
    matches = pattern.findall(content)

    # Filter out code/technical strings
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
        "index", "module", "exports", "Object",
        "Array", "String", "Number", "Boolean",
        "Promise", "Symbol", "Map", "Set",
        "Error", "TypeError", "RangeError",
        "toString", "valueOf", "hasOwnProperty",
        "call", "apply", "bind", "prototype",
        "constructor", "instanceof", "typeof",
    ]

    def is_ui_text(s: str) -> bool:
        s_lower = s.lower()
        # Skip if contains code patterns
        for pat in code_patterns:
            if pat in s_lower:
                return False
        # Skip if too many special chars (likely code)
        special_ratio = sum(1 for c in s if c in '{}[]()<>;=+|&^%$#@!`~\\') / max(len(s), 1)
        if special_ratio > 0.15:
            return False
        # Skip pure numbers/measurements
        if re.match(r'^[0-9.,\s%pxremvhvw]+$', s):
            return False
        # Must have Spanish characters or be meaningful text
        return len(s.split()) >= 4

    filtered = [m.strip() for m in matches if is_ui_text(m)]
    # Deduplicate
    seen = set()
    unique = []
    for m in filtered:
        if m not in seen:
            seen.add(m)
            unique.append(m)
    return unique


def main():
    if len(sys.argv) < 2:
        filepath = "/tmp/genia_bundle.js"
    else:
        filepath = sys.argv[1]

    with open(filepath, "r") as f:
        content = f.read()

    strings = extract_strings(content)

    print(f"Extracted {len(strings)} unique UI text strings:\n")
    for i, s in enumerate(strings, 1):
        # Clean up escape sequences
        s = s.replace("\\n", "\n").replace("\\t", "    ").replace('\\"', '"').replace("\\\\", "\\")
        # Unescape unicode
        s = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), s)
        print(f"[{i}] {s}")
        print("-" * 80)


if __name__ == "__main__":
    main()
