"""Loop conversacional con tool calling y streaming.

Reemplaza la llamada simple a get_llm_response() por un loop que:
1. Envía messages + tool definitions al LLM con streaming activado
2. Si el LLM genera texto → lo streamea al frontend en vivo
3. Si el LLM responde con tool_calls → ejecuta las tools secuencialmente → repite
4. Si el LLM responde con texto → devuelve al usuario

Las interacciones de tipo tool_call y tool_result se persisten en DB dentro del loop.
"""

import json
import uuid
from typing import Callable, Awaitable

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.prompts import SYSTEM_PROMPT
from src.agent.tools import TOOLS
from src.agent.tool_handlers import handle_tool_call
from src.llm.client import get_llm_response_with_tools, stream_llm_response_with_tools
from src.db.queries import save_interaction
from src.db.models import MessageRole

MAX_TOOL_ROUNDS = 10  # seguridad: máximo de rounds de tool calling por mensaje


async def process_message(
    user_message: str,
    history: list[dict],
    db: AsyncSession,
    lead_id: uuid.UUID,
) -> str:
    """Procesa un mensaje del usuario con tool calling y devuelve la respuesta final.

    Versión sin streaming (fallback). Usa get_llm_response_with_tools que espera
    la respuesta completa antes de devolver.

    El historial usa el formato OpenAI de mensajes:
      {"role": "user" | "assistant" | "tool", "content": ..., "tool_calls": ...}

    Durante el loop, si el LLM invoca tools, las ejecuta, persiste las interacciones
    en DB, y continúa hasta obtener una respuesta de texto para el usuario.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_message},
    ]

    for _ in range(MAX_TOOL_ROUNDS):
        response_message = await get_llm_response_with_tools(messages, TOOLS)

        if response_message.tool_calls:
            assistant_msg = {
                "role": "assistant",
                "content": response_message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in response_message.tool_calls
                ],
            }
            messages.append(assistant_msg)

            # Ejecutar tools secuencialmente (AsyncSession no soporta concurrencia)
            for tc in response_message.tool_calls:
                tool_name = tc.function.name
                try:
                    arguments = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}

                result_text = await handle_tool_call(
                    db, lead_id, tool_name, arguments
                )

                await save_interaction(
                    db, lead_id, MessageRole.tool_call, "",
                    tool_name=tool_name,
                    tool_result=result_text,
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_text,
                })

            continue

        if response_message.content:
            return response_message.content

        break

    # Fallback: pedimos una respuesta sin tools
    fallback_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_message},
    ]
    from src.llm.client import get_llm_response
    return await get_llm_response(fallback_messages)


async def process_message_streaming(
    user_message: str,
    history: list[dict],
    db: AsyncSession,
    lead_id: uuid.UUID,
    stream_callback: Callable[[str], Awaitable[None]],
    tool_start_callback: Callable[[], Awaitable[None]] | None = None,
) -> str:
    """Procesa un mensaje del usuario con tool calling + streaming de tokens.

    A diferencia de process_message(), esta versión streamea los tokens de texto
    al frontend a medida que el LLM los genera. Cuando el LLM decide ejecutar tools
    (sin texto que mostrar), se puede mostrar un placeholder vía tool_start_callback.

    Args:
        user_message: texto del usuario
        history: historial en formato OpenAI
        db: sesión de base de datos
        lead_id: ID del lead actual
        stream_callback: llamado con cada token de texto generado
        tool_start_callback: llamado cuando el LLM inicia tool calls (para skeleton UI)

    Returns:
        La respuesta final como texto completo.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_message},
    ]

    for _ in range(MAX_TOOL_ROUNDS):
        accumulated_content = ""
        response_message = None

        async for chunk in stream_llm_response_with_tools(messages, TOOLS):
            if chunk["type"] == "token":
                accumulated_content += chunk["content"]
                await stream_callback(chunk["content"])

            elif chunk["type"] == "done":
                response_message = chunk["message"]

        if response_message is None:
            # Stream terminó sin mensaje completo (no debería ocurrir)
            break

        # Si hay tool_calls → procesar sin mostrar texto al usuario
        if response_message.tool_calls:
            messages.append({
                "role": "assistant",
                "content": response_message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in response_message.tool_calls
                ],
            })

            # Notificar al frontend que estamos procesando tools
            if tool_start_callback:
                await tool_start_callback()

            # Ejecutar tools secuencialmente (AsyncSession no soporta concurrencia)
            for tc in response_message.tool_calls:
                tool_name = tc.function.name
                try:
                    arguments = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}

                result_text = await handle_tool_call(
                    db, lead_id, tool_name, arguments
                )

                await save_interaction(
                    db, lead_id, MessageRole.tool_call, "",
                    tool_name=tool_name,
                    tool_result=result_text,
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_text,
                })

            continue

        # Sin tool_calls → el texto ya se streameó, devolverlo
        final_text = accumulated_content or response_message.content or ""
        if final_text:
            return final_text

        # Ni texto ni tool_calls (raro)
        break

    # Fallback
    fallback_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_message},
    ]
    from src.llm.client import get_llm_response
    return await get_llm_response(fallback_messages)
