import chainlit as cl
from src.agent.agent import run_agent_streaming
from src.db.models import MessageRole, LeadStatus
from src.db.queries import get_or_create_lead, save_interaction, close_lead, count_questions
from src.db.session import async_session

GREETING = (
    "¡Hola! Soy el consultor de IA de GenIA. "
    "Contame un poco sobre vos y tu empresa, así entiendo mejor cómo puedo ayudarte."
)

# Mapeo de tool_name interno → texto amigable para mostrar en el chat.
# Las tools que no están en este diccionario no muestran mensaje (son internas).
# Si el valor es None o string vacío, tampoco se muestra nada.
TOOL_DISPLAY_TEXT: dict[str, str | None] = {
    "registrar_lead": "Tomando nota...",
    "buscar_documentos": "Buscando información...",
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
    history = cl.user_session.get("history", [])
    lead_id = cl.user_session.get("lead_id")

    # 5G — Fast-path: si el mensaje es trivial Y la conversación no arrancó
    # realmente (solo está el saludo inicial), responder sin LLM.
    # Si ya hubo al menos un intercambio user-assistant, el LLM decide —
    # incluso "gracias" puede ser relevante en contexto de diagnóstico.
    normalized = message.content.strip().lower()
    conversation_started = len(history) > 1  # más que solo el greeting
    if normalized in TRIVIAL_RESPONSES and not conversation_started:
        async with async_session() as db:
            await save_interaction(db, lead_id, MessageRole.user, message.content)
            pregunta_numero = await count_questions(db, lead_id) + 1
            response = TRIVIAL_RESPONSES[normalized]
            await save_interaction(
                db, lead_id, MessageRole.assistant, response,
                pregunta_numero=pregunta_numero,
            )

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

    async def stream_token(token: str):
        """Callback: streamea cada token al frontend en vivo."""
        await msg.stream_token(token)

    async def tool_callback(event_type: str, tool_name: str):
        """Callback: notifica inicio/fin de ejecución de tools."""
        nonlocal tool_placeholder_sent
        if event_type == "start" and not tool_placeholder_sent:
            display = TOOL_DISPLAY_TEXT.get(tool_name)
            if display:
                tool_placeholder_sent = True
                await msg.stream_token(f"{display}\n")

    # Una sola sesión de DB para todo el turno
    async with async_session() as db:
        # Guardar mensaje del usuario
        await save_interaction(db, lead_id, MessageRole.user, message.content)

        # Agregar al historial para el LLM
        history.append({"role": "user", "content": message.content})

        # Respuesta del agente con streaming granular (LangGraph)
        response = await run_agent_streaming(
            user_message=message.content,
            history=history,
            db=db,
            lead_id=lead_id,
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
