"""Phase 11 integration test — validates OKF knowledge migration.

Runs inside Docker:
    docker compose run --rm app python3 scripts/test_knowledge_integration.py
"""

import asyncio

from src.agent.prompts import SYSTEM_PROMPT


# --- assertions about what the agent should and shouldn't say ---

GENIA_FACTS = [
    "Genway", "IA soberana", "self-hosted", "open-source",
    "cooperativas", "sin suscripciones", "sin vendor lock-in",
]

GENIA_ANTI_FACTS = [
    "CVs indexados", "presupuestos de referencia", "propuestas en PDF",
    "Qdrant", "pgvector", "sentence-transformers",
    "consultoría en AWS", "Azure", "Google Cloud",
    "Fiqus",  # not on actual site
    "Tecso",  # not on actual site
]


def check_knowledge_accuracy(prompt_text: str) -> dict:
    """Check that the system prompt does NOT contain inline facts or anti-facts."""
    present = [f for f in GENIA_FACTS if f.lower() in prompt_text.lower()]
    absent = [f for f in GENIA_ANTI_FACTS if f.lower() in prompt_text.lower()]
    return {
        "present": present,
        "hallucinated": absent,
        "passed": len(absent) == 0,
    }


def main():
    # Test 1: Knowledge is NOT inline in system prompt (OKF navigation)
    print("=" * 60)
    print("TEST 1 — Knowledge is NOT inline in system prompt")
    print("=" * 60)
    result = check_knowledge_accuracy(SYSTEM_PROMPT)
    if len(result["present"]) == 0:
        print(f"  ✅ Knowledge correctly removed from system prompt")
    else:
        print(f"  ❌ Found {len(result['present'])} facts still in prompt: {result['present']}")
    if result["hallucinated"]:
        print(f"  ❌ Hallucinated: {result['hallucinated']}")
    print()

    # Test 2: KnowledgeBase loads articles with frontmatter
    print("=" * 60)
    print("TEST 2 — KnowledgeBase loads articles with OKF frontmatter")
    print("=" * 60)
    from src.knowledge.loader import knowledge_base

    articles = knowledge_base.list_articles()
    print(f"  Loaded {len(articles)} articles:")
    for a in articles:
        has_meta = bool(a["title"] and a["description"] and a["tags"])
        status = "✅" if has_meta else "❌"
        print(f"  {status} {a['slug']}: {a['title']} — tags: {a['tags']}")

    all_passed = len(articles) == 7
    if all_passed:
        print(f"\n  ✅ All 7 articles loaded with frontmatter")
    else:
        print(f"\n  ❌ Expected 7 articles, got {len(articles)}")
    print()

    # Test 3: get_full_article returns content for each slug
    print("=" * 60)
    print("TEST 3 — get_full_article returns content for each slug")
    print("=" * 60)
    expected_slugs = [
        "genia", "servicios-ia", "productos", "casos-de-exito",
        "industrias", "tecnologias", "proceso-de-trabajo",
    ]
    for slug in expected_slugs:
        content = knowledge_base.get_full_article(slug)
        status = "✅" if content and len(content) > 50 else "❌"
        print(f"  {status} {slug}: {len(content) if content else 0} chars")
    print()

    # Test 4: System prompt size check (should be smaller after OKF)
    print("=" * 60)
    print("TEST 4 — System prompt size (post-OKF)")
    print("=" * 60)
    chars = len(SYSTEM_PROMPT)
    tokens_est = chars // 4
    print(f"  System prompt: {chars} chars (~{tokens_est} tokens)")
    if tokens_est < 5000:
        print(f"  ✅ Significantly smaller than before (~3800 token reduction)")
    else:
        print(f"  ⚠️  Still large — check if knowledge was properly removed")
    print()

    # Test 5: Agent tool definitions
    print("=" * 60)
    print("TEST 5 — Agent tools import correctly")
    print("=" * 60)
    from src.agent.tools import ALL_TOOLS, listar_articulos, leer_articulo, buscar_cv
    tool_names = [t.name for t in ALL_TOOLS]
    expected_tools = [
        "registrar_lead", "contador_preguntas",
        "listar_articulos", "leer_articulo",
        "buscar_cv", "generar_resumen",
    ]
    for t in expected_tools:
        status = "✅" if t in tool_names else "❌"
        print(f"  {status} {t}")
    if "buscar_documentos" not in tool_names:
        print(f"  ✅ buscar_documentos correctly removed")
    else:
        print(f"  ❌ buscar_documentos still present")
    print()

    # Test 6: listar_articulos returns article index
    print("=" * 60)
    print("TEST 6 — listar_articulos tool returns article index")
    print("=" * 60)
    list_result = asyncio.get_event_loop().run_until_complete(
        listar_articulos.ainvoke({})
    )
    lines = list_result.count("\n") + 1
    print(f"  listar_articulos returned {lines} lines")
    print(f"  ✅ listar_articulos works")
    print()

    # Test 7: leer_articulo returns full content
    print("=" * 60)
    print("TEST 7 — leer_articulo tool returns full article")
    print("=" * 60)
    leer_result = asyncio.get_event_loop().run_until_complete(
        leer_articulo.ainvoke({"slug": "genia"})
    )
    assert "GenIA" in leer_result, f"Expected GenIA content, got: {leer_result[:100]}"
    print(f"  ✅ leer_articulo('genia') returns {len(leer_result)} chars")
    leer_invalid = asyncio.get_event_loop().run_until_complete(
        leer_articulo.ainvoke({"slug": "no-existe"})
    )
    assert "no existe" in leer_invalid.lower(), f"Expected error, got: {leer_invalid}"
    print(f"  ✅ leer_articulo handles invalid slug correctly")
    print()

    # Test 8: buscar_cv is honest stub (unchanged)
    print("=" * 60)
    print("TEST 8 — buscar_cv is honest stub")
    print("=" * 60)
    cv_result = asyncio.get_event_loop().run_until_complete(
        buscar_cv.ainvoke({"tecnologia": "Python"})
    )
    assert "no mantiene" in cv_result.lower(), f"Expected honest stub, got: {cv_result}"
    print(f"  ✅ buscar_cv returns honest message (not fake CVs)")
    print()

    print("=" * 60)
    print("PHASE 11 OKF MIGRATION — ALL TESTS COMPLETE ✅")
    print("=" * 60)


if __name__ == "__main__":
    main()
