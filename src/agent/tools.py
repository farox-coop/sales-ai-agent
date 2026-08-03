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
)
from src.db.models import Lead, LeadStatus, MessageRole
from src.knowledge.loader import knowledge_base

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
async def listar_articulos(config: RunnableConfig = None) -> str:
    """Lista los artículos disponibles en la base de conocimiento de GenIA, con
    título, descripción y tags.

    Usala primero para orientarte antes de leer el contenido completo de un
    artículo específico con leer_articulo. No tenés el conocimiento de GenIA
    precargado: para cualquier pregunta sobre GenIA, sus servicios, productos,
    tecnologías o experiencia, empezar por acá.
    """
    articles = knowledge_base.list_articles()
    lines = [
        f"- {a['slug']}: {a['title']} — {a['description']} [{', '.join(a['tags'])}]"
        for a in articles
    ]
    return "\n".join(lines)


@tool
async def leer_articulo(slug: str, config: RunnableConfig = None) -> str:
    """Devuelve el contenido completo de un artículo de la base de conocimiento de
    GenIA, identificado por su slug (obtenido con listar_articulos).

    El artículo puede contener links a otros artículos relacionados con el formato
    [[slug]] — seguilos con leer_articulo si necesitás más contexto.

    Args:
        slug: identificador del artículo, ej. 'casos-de-exito'.
    """
    content = knowledge_base.get_full_article(slug.strip())
    if not content:
        return (
            f"No existe un artículo con slug '{slug}'. "
            f"Usá listar_articulos para ver los disponibles."
        )
    return content


@tool
async def buscar_cv(tecnologia: str, config: RunnableConfig = None) -> str:
    """Busca perfiles profesionales (CVs) en la base de GenIA con experiencia en
    una tecnología o área específica.

    IMPORTANTE: GenIA actualmente no mantiene una base de CVs indexados. Esta tool
    devuelve un mensaje informativo para que puedas responder al lead con honestidad.
    Si el lead pregunta por perfiles específicos, derivá la consulta al equipo
    comercial para que evalúen disponibilidad de recursos.

    Args:
        tecnologia: Tecnología o skill a buscar, ej. 'Python', 'Computer Vision', 'RAG'.
    """
    return (
        f"GenIA no mantiene una base de CVs indexados. No hay perfiles disponibles "
        f"para '{tecnologia}'.\n\n"
        f"Si el lead pregunta por perfiles o experiencia en tecnologías específicas, "
        f"respondé con honestidad: 'Actualmente no tenemos una base de CVs públicos, "
        f"pero si te interesa podemos conversar con el equipo comercial para evaluar "
        f"la disponibilidad de recursos con experiencia en {tecnologia}.'"
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


ALL_TOOLS = [
    registrar_lead,
    contador_preguntas,
    listar_articulos,
    leer_articulo,
    buscar_cv,
    generar_resumen,
]
