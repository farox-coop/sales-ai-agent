"""Implementación de cada tool del agente.

Cada handler recibe el contexto (db session + lead_id) y los argumentos
que el LLM pasó al invocar la tool. Devuelve un string con el resultado
que se inyecta en el historial como mensaje de tipo "tool".
"""

import json
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.queries import (
    update_lead,
    count_questions,
    get_lead_interactions,
    close_lead,
    get_active_documents,
)
from src.db.models import Lead, LeadStatus, MessageRole

MAX_DIAGNOSTIC_QUESTIONS = 12


async def handle_tool_call(
    db: AsyncSession,
    lead_id: uuid.UUID,
    tool_name: str,
    arguments: dict,
) -> str:
    """Despacha la tool call al handler correspondiente."""
    handlers = {
        "registrar_lead": handle_registrar_lead,
        "contador_preguntas": handle_contador_preguntas,
        "buscar_documentos": handle_buscar_documentos,
        "buscar_cv": handle_buscar_cv,
        "generar_resumen": handle_generar_resumen,
    }

    handler = handlers.get(tool_name)
    if handler is None:
        return json.dumps({"error": f"Tool desconocida: {tool_name}"})

    try:
        result = await handler(db, lead_id, arguments)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


async def handle_registrar_lead(
    db: AsyncSession, lead_id: uuid.UUID, args: dict
) -> dict:
    """Actualiza incrementalmente los datos del lead en DB.

    Solo persiste campos cuyo valor realmente cambió respecto a lo que ya
    está en la base. Si todos los campos ya tenían el valor proporcionado,
    no ejecuta UPDATE y lo informa claramente para que el LLM aprenda a no
    llamar la tool sin datos nuevos.
    """
    # Obtener lead actual para comparar
    lead = await db.get(Lead, lead_id)
    if not lead:
        return {"status": "error", "msg": "Lead no encontrado."}

    updates = {}
    unchanged = []
    for field in ("nombre", "email", "empresa", "cargo"):
        value = args.get(field)
        if not value or not value.strip():
            continue
        value = value.strip()

        current = getattr(lead, field, None)
        if current == value:
            unchanged.append(field)
        else:
            updates[field] = value

    if not updates:
        return {
            "status": "ok",
            "updated": [],
            "unchanged": unchanged,
            "msg": (
                "Sin datos nuevos para registrar (todos los campos proporcionados "
                "ya tenían el mismo valor en la base de datos)."
            ),
        }

    await update_lead(db, lead_id, **updates)
    return {
        "status": "ok",
        "updated": list(updates.keys()),
        "unchanged": unchanged,
        "msg": (
            f"Datos actualizados: {', '.join(updates.keys())}."
            + (f" Sin cambios: {', '.join(unchanged)}." if unchanged else "")
        ),
    }


async def handle_contador_preguntas(
    db: AsyncSession, lead_id: uuid.UUID, args: dict
) -> dict:
    """Devuelve cuántas preguntas de diagnóstico se hicieron y cuántas quedan."""
    count = await count_questions(db, lead_id)
    remaining = max(0, MAX_DIAGNOSTIC_QUESTIONS - count)
    return {
        "preguntas_hechas": count,
        "preguntas_restantes": remaining,
        "maximo": MAX_DIAGNOSTIC_QUESTIONS,
    }


async def handle_buscar_documentos(
    db: AsyncSession, lead_id: uuid.UUID, args: dict
) -> dict:
    """Busca documentos en la base (mock hasta integrar Qdrant en Plan 5)."""
    query = args.get("query", "")
    tipo = args.get("tipo")

    # Búsqueda en SQL (por tipo y nombre) como fallback hasta tener Qdrant
    documentos = await get_active_documents(db, tipo=tipo)

    # Filtro básico por texto en nombre
    query_lower = query.lower()
    matches = [
        {
            "id": str(doc.id),
            "nombre": doc.nombre,
            "tipo": doc.tipo.value if doc.tipo else "otro",
        }
        for doc in documentos
        if query_lower in doc.nombre.lower()
    ]

    if not matches:
        # Sin resultados: devolvemos lista vacía, no error.
        # El LLM decidirá si menciona que no se encontraron docs o sigue de largo.
        return {
            "query": query,
            "tipo": tipo,
            "resultados": [],
            "total": 0,
            "nota": "Búsqueda preliminar (Qdrant pendiente de integración).",
        }

    return {
        "query": query,
        "tipo": tipo,
        "resultados": matches[:5],
        "total": len(matches),
    }


async def handle_buscar_cv(
    db: AsyncSession, lead_id: uuid.UUID, args: dict
) -> dict:
    """Busca CVs por tecnología (mock hasta integrar Qdrant en Plan 5)."""
    tecnologia = args.get("tecnologia", "")

    # Buscar solo documentos tipo 'cv' con matching básico por nombre
    documentos = await get_active_documents(db, tipo="cv")
    query_lower = tecnologia.lower()
    matches = [
        {
            "id": str(doc.id),
            "nombre": doc.nombre,
        }
        for doc in documentos
        if query_lower in doc.nombre.lower()
    ]

    return {
        "tecnologia": tecnologia,
        "resultados": matches[:5],
        "total": len(matches),
    }


async def handle_generar_resumen(
    db: AsyncSession, lead_id: uuid.UUID, args: dict
) -> dict:
    """Genera el resumen del diagnóstico y cierra el lead.

    La tool:
    1. Recupera todas las interacciones del lead
    2. Marca el lead como completado
    3. Devuelve datos para que el LLM genere el resumen

    El texto del resumen lo genera el LLM en base al historial,
    no esta tool. Esta tool solo hace el commit en DB.
    """
    # Recuperar interacciones para contexto
    interacciones = await get_lead_interactions(db, lead_id)
    total_mensajes = len(interacciones)
    preguntas_count = sum(
        1 for i in interacciones if i.rol == MessageRole.assistant
    )

    # Obtener datos del lead para incluir en el resumen
    lead = await db.get(Lead, lead_id)

    # Cerrar el lead como completado
    await close_lead(db, lead_id, LeadStatus.completado)

    return {
        "status": "ok",
        "lead_completado": True,
        "total_interacciones": total_mensajes,
        "preguntas_diagnostico": preguntas_count,
        "lead_nombre": lead.nombre if lead else None,
        "lead_empresa": lead.empresa if lead else None,
        "lead_email": lead.email if lead else None,
        "lead_cargo": lead.cargo if lead else None,
        "instruccion": (
            "El lead fue marcado como completado en la base de datos. "
            "AHORA generá un resumen estructurado del diagnóstico basado en toda la "
            "conversación. El resumen debe incluir: (1) Perfil de la empresa, "
            "(2) Madurez de IA estimada, (3) Casos de uso identificados, "
            "(4) Próximos pasos recomendados. Mostrá este resumen al lead y despedite."
        ),
    }
