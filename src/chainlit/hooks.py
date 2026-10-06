import logging

import chainlit as cl
from src.agent.agent import run_agent_streaming
from src.config import settings
from src.db.models import MessageRole, LeadStatus
from src.db.queries import get_or_create_lead, save_interaction, close_lead, count_questions
from src.db.session import async_session

logger = logging.getLogger(__name__)

GREETING = (
    "¡Hola! Soy el asistente de GenIA. "
    "¿En qué te puedo ayudar?"
)

# Mensaje de fallback cuando algo falla y no podemos generar una respuesta real.
# Evita que el chat quede colgado sin responder.
ERROR_MESSAGE = (
    "Perdón, tuve un inconveniente técnico y no pude procesar tu mensaje. "
    "Por favor intentá de nuevo en unos minutos."
)

# Mapeo de tool_name interno → texto amigable para mostrar en el chat.
# Las tools que no están en este diccionario no muestran mensaje (son internas).
# Si el valor es None o string vacío, tampoco se muestra nada.
TOOL_DISPLAY_TEXT: dict[str, str | None] = {
    "registrar_lead": "Tomando nota...",
    "solicitar_contacto": "Registrando tu solicitud...",
    "listar_articulos": "Consultando información...",
    "leer_articulo": "Consultando información...",
    "buscar_cv": "Buscando perfiles...",
    "generar_resumen": "Preparando tu diagnóstico...",
    # contador_preguntas es puramente interno, no se muestra.
}

# 5G — Fast-path: respuestas predefinidas para mensajes triviales.
# Evita una llamada completa al LLM (~3.5s) para respuestas predecibles.
# IMPORTANTE: solo se aplica cuando la conversación no arrancó realmente
# (history <= 1, es decir, solo el saludo inicial). Si ya hubo un intercambio
# real, dejamos que el LLM maneje el mensaje — incluso "gracias" u "ok" pueden
# ser confirmaciones a un resumen o pregunta del agente, no mensajes vacíos.
# "si" fue removido explícitamente: es la palabra más dependiente de contexto
# y causó un descarrilamiento en la charla con Peter (turno 13-16).
TRIVIAL_RESPONSES: dict[str, str] = {
    "gracias": "¡De nada! ¿Hay algo más en lo que pueda ayudarte?",
    "muchas gracias": "¡De nada! ¿Hay algo más en lo que pueda ayudarte?",
    "bueno": "¿Hay algo más que quieras profundizar?",
}


@cl.on_chat_start
async def start():
    # Modo mantenimiento: rechazar el inicio de la conversación.
    if settings.maintenance_mode:
        await cl.Message(content=settings.maintenance_message).send()
        return

    # Crear o recuperar lead en DB
    session_id = cl.user_session.get("id") or cl.context.session.id
    cl.user_session.set("session_id", session_id)

    async with async_session() as db:
        lead = await get_or_create_lead(db, session_id)
        cl.user_session.set("lead_id", lead.id)

    # Historial: arranca con el saludo del asistente ya incluido.
    # Solo guardamos mensajes user/assistant visibles (no tool_calls internos).
    cl.user_session.set("history", [
        {"role": "assistant", "content": GREETING},
    ])

    # Mensaje de presentacion instantaneo (sin llamada al LLM)
    await cl.Message(content=GREETING).send()


@cl.on_message
async def on_message(message: cl.Message):
    # Modo mantenimiento: cortar también sesiones ya abiertas.
    if settings.maintenance_mode:
        await cl.Message(content=settings.maintenance_message).send()
        return

    history = cl.user_session.get("history", [])
    lead_id = cl.user_session.get("lead_id")
    session_id = cl.user_session.get("session_id")

    # 5G — Fast-path: si el mensaje es trivial Y la conversación no arrancó
    # realmente (solo está el saludo inicial), responder sin LLM.
    # Si ya hubo al menos un intercambio user-assistant, el LLM decide —
    # incluso "gracias" puede ser relevante en contexto de diagnóstico.
    normalized = message.content.strip().lower()
    conversation_started = len(history) > 1  # más que solo el greeting
    if normalized in TRIVIAL_RESPONSES and not conversation_started:
        try:
            async with async_session() as db:
                await save_interaction(db, lead_id, MessageRole.user, message.content)
                pregunta_numero = await count_questions(db, lead_id) + 1
                response = TRIVIAL_RESPONSES[normalized]
                await save_interaction(
                    db, lead_id, MessageRole.assistant, response,
                    pregunta_numero=pregunta_numero,
                )
        except Exception:
            logger.exception("Error en fast-path del lead %s", lead_id)
            response = ERROR_MESSAGE

        history.append({"role": "user", "content": message.content})
        history.append({"role": "assistant", "content": response})
        cl.user_session.set("history", history)

        await cl.Message(content=response).send()
        return

    # 5A + 5D — Streaming: mensaje vacío que se llena incrementalmente
    msg = cl.Message(content="")
    await msg.send()

    # 5D — Skeleton durante tool execution: si el LLM va directo a tools sin
    # generar texto, mostramos un placeholder para que el lead no vea pantalla en blanco.
    tool_placeholder_sent = False
    streamed = False

    async def stream_token(token: str):
        """Callback: streamea cada token al frontend en vivo."""
        nonlocal streamed
        streamed = True
        await msg.stream_token(token)

    async def tool_callback(event_type: str, tool_name: str):
        """Callback: notifica inicio/fin de ejecución de tools."""
        nonlocal tool_placeholder_sent
        if event_type == "start" and not tool_placeholder_sent:
            display = TOOL_DISPLAY_TEXT.get(tool_name)
            if display:
                tool_placeholder_sent = True
                await msg.stream_token(f"{display}\n")

    # El mensaje del usuario entra al historial sí o sí (también si falla el agente).
    history.append({"role": "user", "content": message.content})

    response = None
    try:
        async with async_session() as db:
            # Guardar mensaje del usuario
            await save_interaction(db, lead_id, MessageRole.user, message.content)

            # Respuesta del agente con streaming granular (LangGraph)
            response = await run_agent_streaming(
                user_message=message.content,
                history=history,
                session_factory=async_session,
                lead_id=lead_id,
                session_id=session_id,
                stream_callback=stream_token,
                tool_callback=tool_callback,
            )

            # Calcular número de pregunta
            pregunta_numero = await count_questions(db, lead_id) + 1

            # Guardar respuesta final del asistente
            await save_interaction(
                db, lead_id, MessageRole.assistant, response,
                pregunta_numero=pregunta_numero,
            )
    except Exception:
        # Si algo falla, el chat no debe quedar colgado: mostramos un mensaje
        # de error y lo persistimos (best-effort) para no perder el turno.
        logger.exception("Error procesando el mensaje del lead %s", lead_id)
        response = ERROR_MESSAGE

        try:
            async with async_session() as db:
                await save_interaction(db, lead_id, MessageRole.assistant, response)
        except Exception:
            logger.exception("No se pudo persistir el mensaje de error del lead %s", lead_id)

        separator = "\n\n" if streamed else ""
        await msg.stream_token(f"{separator}{ERROR_MESSAGE}")

    # Agregar respuesta al historial para el próximo turno
    history.append({"role": "assistant", "content": response})
    cl.user_session.set("history", history)

    # Finalizar el mensaje (Chainlit lo da por completo)
    await msg.update()


@cl.on_stop
async def on_stop():
    lead_id = cl.user_session.get("lead_id")
    if lead_id:
        async with async_session() as db:
            await close_lead(db, lead_id, LeadStatus.abandonado)
