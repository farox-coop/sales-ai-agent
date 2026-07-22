"""Tools del agente definidas con el decorador @tool de LangChain.

Cada tool recibe contexto de ejecución (db, lead_id) via RunnableConfig.
Los schemas JSON para el LLM se infieren automáticamente de los type hints y docstrings.
"""

import uuid
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
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


def _get_context(config: RunnableConfig) -> tuple[AsyncSession, uuid.UUID]:
    """Extrae db y lead_id del RunnableConfig inyectado en la ejecución del agente."""
    db = config["configurable"]["db"]
    lead_id = config["configurable"]["lead_id"]
    return db, lead_id


@tool
async def registrar_lead(
    nombre: str = "",
    email: str = "",
    empresa: str = "",
    cargo: str = "",
    config: RunnableConfig = None,
) -> str:
    """Registra o actualiza los datos de identificación del lead en la base de datos.

    Llamala SOLO cuando el lead proporcione un dato NUEVO que no hayas registrado
    antes (nombre, email, empresa, cargo). No la llames por las dudas o 'para
    verificar': la tool te informa si los datos ya estaban registrados y no hubo
    cambios. Regla práctica: si en este turno el lead no dijo nada nuevo sobre su
    identidad, no llames a esta tool.

    Args:
        nombre: Nombre completo del lead (ej. 'Juan Perez').
        email: Correo electrónico del lead (ej. 'juan@empresa.com').
        empresa: Nombre de la empresa donde trabaja.
        cargo: Cargo o rol del lead en la empresa (ej. 'CTO', 'Gerente de Innovación').
    """
    db, lead_id = _get_context(config)

    lead = await db.get(Lead, lead_id)
    if not lead:
        return "Error: Lead no encontrado."

    updates = {}
    unchanged = []
    for field in ("nombre", "email", "empresa", "cargo"):
        value = locals().get(field)
        if not value or not value.strip():
            continue
        value = value.strip()

        current = getattr(lead, field, None)
        if current == value:
            unchanged.append(field)
        else:
            updates[field] = value

    if not updates:
        campos = ", ".join(unchanged) if unchanged else "ninguno"
        return (
            f"Sin datos nuevos para registrar. Los campos {campos} "
            f"ya tenían el mismo valor en la base de datos."
        )

    await update_lead(db, lead_id, **updates)
    msg = f"Datos actualizados: {', '.join(updates.keys())}."
    if unchanged:
        msg += f" Sin cambios: {', '.join(unchanged)}."
    return msg


@tool
async def contador_preguntas(config: RunnableConfig = None) -> str:
    """Devuelve cuántas preguntas de diagnóstico se hicieron hasta ahora y cuántas
    quedan disponibles (el máximo es 12).

    Llamala para decidir si seguís explorando un dominio, si pasás a otro, o si
    vas cerrando. También para saber cuándo avisar al lead que quedan pocas preguntas.
    """
    db, lead_id = _get_context(config)
    count = await count_questions(db, lead_id)
    remaining = max(0, MAX_DIAGNOSTIC_QUESTIONS - count)
    return (
        f"Preguntas hechas: {count}. "
        f"Preguntas restantes: {remaining}. "
        f"Máximo: {MAX_DIAGNOSTIC_QUESTIONS}."
    )


@tool
async def buscar_documentos(
    query: str,
    tipo: str = "",
    config: RunnableConfig = None,
) -> str:
    """Busca documentos relevantes en la base de conocimiento de GenIA: propuestas
    comerciales, presupuestos, casos de éxito, documentos técnicos.

    Usala cuando el lead menciona una tecnología específica, un caso de uso, o
    pregunta si GenIA tiene experiencia en algo. También si querés respaldar una
    recomendación con un caso real.

    Args:
        query: Texto de búsqueda, ej. 'machine learning en logística' o 'automatización de procesos'.
        tipo: Tipo de documento a buscar. Opciones: propuesta, cv, presupuesto, otro. Opcional.
    """
    db, _ = _get_context(config)

    tipo_filtro = tipo if tipo and tipo.strip() else None
    documentos = await get_active_documents(db, tipo=tipo_filtro)

    query_lower = query.lower()
    matches = [
        f"- {doc.nombre} (tipo: {doc.tipo.value if doc.tipo else 'otro'})"
        for doc in documentos
        if query_lower in doc.nombre.lower()
    ]

    if not matches:
        return (
            f"No se encontraron documentos para '{query}'"
            + (f" de tipo '{tipo}'" if tipo else "")
            + ". Búsqueda preliminar (Qdrant pendiente de integración)."
        )

    return (
        f"Resultados para '{query}'"
        + (f" (tipo: {tipo})" if tipo else "")
        + f" — {len(matches)} encontrados:\n"
        + "\n".join(matches[:5])
    )


@tool
async def buscar_cv(tecnologia: str, config: RunnableConfig = None) -> str:
    """Busca perfiles profesionales (CVs) en la base de GenIA que tengan experiencia
    en una tecnología o área específica.

    Usala cuando el lead pregunta '¿tienen a alguien que sepa X?' o '¿conocen gente
    con experiencia en Y?'. Responde con un resumen de los perfiles encontrados.

    Args:
        tecnologia: Tecnología o skill a buscar, ej. 'Python', 'Computer Vision', 'RAG'.
    """
    db, _ = _get_context(config)

    documentos = await get_active_documents(db, tipo="cv")
    query_lower = tecnologia.lower()
    matches = [
        f"- {doc.nombre}"
        for doc in documentos
        if query_lower in doc.nombre.lower()
    ]

    if not matches:
        return f"No se encontraron CVs con experiencia en '{tecnologia}'."

    return (
        f"CVs encontrados para '{tecnologia}' — {len(matches)} resultados:\n"
        + "\n".join(matches[:5])
    )


@tool
async def generar_resumen(config: RunnableConfig = None) -> str:
    """Genera el resumen estructurado del diagnóstico, lo guarda en la base de datos
    y cambia el estado del lead a 'completado'.

    Llamala ÚNICAMENTE cuando ya hayas terminado todas las preguntas (llegaste a 12
    o el lead dio un panorama completo antes) y sea momento de cerrar la conversación.
    La tool devuelve datos para que generes el resumen y se lo muestres al lead junto
    con la despedida.
    """
    db, lead_id = _get_context(config)

    interacciones = await get_lead_interactions(db, lead_id)
    total_mensajes = len(interacciones)
    preguntas_count = sum(
        1 for i in interacciones if i.rol == MessageRole.assistant
    )

    lead = await db.get(Lead, lead_id)

    await close_lead(db, lead_id, LeadStatus.completado)

    return (
        f"Lead completado. Datos para el resumen:\n"
        f"- Nombre: {lead.nombre if lead else 'N/A'}\n"
        f"- Empresa: {lead.empresa if lead else 'N/A'}\n"
        f"- Email: {lead.email if lead else 'N/A'}\n"
        f"- Cargo: {lead.cargo if lead else 'N/A'}\n"
        f"- Total interacciones: {total_mensajes}\n"
        f"- Preguntas de diagnóstico: {preguntas_count}\n"
        f"\nAHORA generá un resumen estructurado del diagnóstico basado en toda "
        f"la conversación. El resumen debe incluir: (1) Perfil de la empresa, "
        f"(2) Madurez de IA estimada, (3) Casos de uso identificados, "
        f"(4) Próximos pasos recomendados. Mostrá este resumen al lead y despedite."
    )


# Lista de tools que el agente expone al LLM
ALL_TOOLS = [
    registrar_lead,
    contador_preguntas,
    buscar_documentos,
    buscar_cv,
    generar_resumen,
]
