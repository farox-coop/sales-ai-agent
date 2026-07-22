"""Agente React con LangGraph: creación del agente y ejecución con streaming granular.

Reemplaza el loop manual de tool calling + streaming artesanal (~360 líneas entre
client.py y conversation.py) por create_react_agent + astream_events().

El streaming es granular: tokens en vivo, notificaciones on_tool_start/on_tool_end.
"""

from typing import Callable, Awaitable

from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from src.config import settings
from src.agent.tools import ALL_TOOLS
from src.agent.prompts import SYSTEM_PROMPT


def _build_model() -> ChatOpenAI:
    """Crea el modelo ChatOpenAI apuntando al AI gateway de GenIA.

    ChatOpenAI usa el protocolo OpenAI-compatible del gateway — el vendor lock-in
    es irrelevante porque el gateway traduce a cualquier provider (Anthropic,
    DeepSeek, etc.) de forma transparente.
    """
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )


def build_agent():
    """Crea el agente React con tools y modelo configurado.

    Se llama una sola vez al iniciar la app (singleton). El agente compilado
    es seguro para reutilizar entre requests concurrentes — cada ejecución
    recibe su propio estado y config via RunnableConfig.
    """
    model = _build_model()
    return create_react_agent(
        model=model,
        tools=ALL_TOOLS,
        prompt=SystemMessage(content=SYSTEM_PROMPT),
    )


# Singleton: el agente se crea una vez, se reusa por request
agent = build_agent()


async def run_agent_streaming(
    user_message: str,
    history: list[dict],
    db,
    lead_id,
    stream_callback: Callable[[str], Awaitable[None]],
    tool_callback: Callable[[str, str], Awaitable[None]],
) -> str:
    """Ejecuta el agente con streaming granular de tokens y tools.

    Usa astream_events(version="v2") que emite eventos tipados:
    - on_chat_model_start: el LLM empieza a generar (reseteamos acumulador)
    - on_chat_model_stream: token de texto → stream_callback
    - on_tool_start: el agente va a ejecutar una tool → tool_callback("start", name)
    - on_tool_end: la tool terminó → tool_callback("end", name)

    Args:
        user_message: texto del usuario.
        history: historial en formato {"role": ..., "content": ...}.
        db: AsyncSession de SQLAlchemy.
        lead_id: UUID del lead actual.
        stream_callback: llamado con cada token de texto generado.
        tool_callback: llamado en on_tool_start / on_tool_end con (event_type, tool_name).

    Returns:
        La respuesta final del agente como texto completo.
    """
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        *_dict_history_to_langchain(history),
        HumanMessage(content=user_message),
    ]

    config = RunnableConfig(configurable={"db": db, "lead_id": lead_id})

    accumulated_content = ""

    async for event in agent.astream_events(
        {"messages": messages},
        config=config,
        version="v2",
    ):
        kind = event["event"]

        if kind == "on_chat_model_start":
            # Nueva ronda del LLM → resetear acumulador para quedarnos solo
            # con el texto de la última ronda (la respuesta final al usuario)
            accumulated_content = ""

        elif kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                accumulated_content += chunk.content
                await stream_callback(chunk.content)

        elif kind == "on_tool_start":
            name = event.get("name", "")
            await tool_callback("start", name)

        elif kind == "on_tool_end":
            name = event.get("name", "")
            await tool_callback("end", name)

    return accumulated_content


def _dict_history_to_langchain(history: list[dict]) -> list:
    """Convierte historial en formato {"role": ..., "content": ...} a mensajes LangChain."""
    mapping = {
        "user": HumanMessage,
        "assistant": AIMessage,
        "system": SystemMessage,
    }
    return [
        mapping[m["role"]](content=m["content"])
        for m in history
        if m["role"] in mapping
    ]
