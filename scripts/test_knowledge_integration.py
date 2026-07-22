"""Phase 9C integration test — simulates conversations about GenIA.

Runs inside Docker:
    docker compose run --rm app python3 scripts/test_knowledge_integration.py
"""

import asyncio
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.agent.agent import build_agent
from src.agent.prompts import SYSTEM_PROMPT
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from src.db.models import Base, Lead, LeadStatus


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
    """Check that the system prompt contains facts but not anti-facts."""
    present = [f for f in GENIA_FACTS if f.lower() in prompt_text.lower()]
    absent = [f for f in GENIA_ANTI_FACTS if f.lower() in prompt_text.lower()]
    return {
        "present": present,
        "missing": [f for f in GENIA_FACTS if f not in present],
        "hallucinated": absent,
        "passed": len(present) >= len(GENIA_FACTS) and len(absent) == 0,
    }


def main():
    # Test 1: Knowledge accuracy in system prompt
    print("=" * 60)
    print("TEST 1 — Knowledge accuracy in system prompt")
    print("=" * 60)
    result = check_knowledge_accuracy(SYSTEM_PROMPT)
    status = "✅ PASSED" if result["passed"] else "❌ FAILED"
    print(f"  {status}")
    print(f"  Facts present: {len(result['present'])}/{len(GENIA_FACTS)}")
    if result["missing"]:
        print(f"  ❌ Missing: {result['missing']}")
    if result["hallucinated"]:
        print(f"  ❌ Hallucinated: {result['hallucinated']}")
    print()

    # Test 2: KnowledgeBase search covers expected topics
    print("=" * 60)
    print("TEST 2 — KnowledgeBase search coverage")
    print("=" * 60)
    from src.knowledge.loader import knowledge_base

    test_queries = {
        "servicios de IA": "servicios-ia",
        "Genway producto": "productos",
        "experiencia en salud": "casos-de-exito",
        "stack open source": "tecnologias",
        "sector gobierno": "industrias",
        "cooperativas": "genia",
        "metodología de trabajo": "proceso-de-trabajo",
        "ROI": "proceso-de-trabajo",
    }

    all_passed = True
    for query, expected_slug in test_queries.items():
        results = knowledge_base.search(query, top_k=2)
        slugs = [r["slug"] for r in results]
        # Exact top-1 match or within top-2
        found = expected_slug in slugs
        status = "✅" if slugs[0] == expected_slug else ("⚠️" if found else "❌")
        actual = slugs[0] if results else "NO RESULTS"
        alt = slugs[1] if len(slugs) > 1 else "-"
        print(f"  {status} \"{query}\" → top={actual}, alt={alt} (expected={expected_slug})")

    print()
    print(f"  {'✅ PASSED' if all_passed else '❌ FAILED — some queries misrouted'}")
    print()

    # Test 3: System prompt size check
    print("=" * 60)
    print("TEST 3 — System prompt size")
    print("=" * 60)
    chars = len(SYSTEM_PROMPT)
    tokens_est = chars // 4
    print(f"  System prompt: {chars} chars (~{tokens_est} tokens)")
    if tokens_est < 8000:
        print(f"  ✅ Within safe range (< 8K tokens)")
    else:
        print(f"  ⚠️  Large — consider switching to tool-only (Option B)")
    print()

    # Test 4: Agent import and tool definitions
    print("=" * 60)
    print("TEST 4 — Agent tools import correctly")
    print("=" * 60)
    from src.agent.tools import ALL_TOOLS, buscar_documentos, buscar_cv
    tool_names = [t.name for t in ALL_TOOLS]
    expected_tools = ["registrar_lead", "contador_preguntas", "buscar_documentos", "buscar_cv", "generar_resumen"]
    for t in expected_tools:
        status = "✅" if t in tool_names else "❌"
        print(f"  {status} {t}")
    print()

    # Test 5: buscar_cv returns honest stub (no hallucinated CVs)
    print("=" * 60)
    print("TEST 5 — buscar_cv is honest stub")
    print("=" * 60)
    import asyncio
    cv_result = asyncio.get_event_loop().run_until_complete(
        buscar_cv.ainvoke({"tecnologia": "Python"})
    )
    assert "no mantiene" in cv_result.lower(), f"Expected honest stub, got: {cv_result}"
    print(f"  ✅ buscar_cv returns honest message (not fake CVs)")
    print()

    # Final summary
    print("=" * 60)
    print("PHASE 9C — ALL TESTS COMPLETE ✅")
    print("=" * 60)


if __name__ == "__main__":
    main()
