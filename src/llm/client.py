import httpx
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage
from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
    Function,
)
from src.config import settings

client = AsyncOpenAI(
    api_key=settings.llm_api_key,
    base_url=settings.llm_base_url,
    timeout=30.0,
    max_retries=2,
    http_client=httpx.AsyncClient(
        limits=httpx.Limits(
            max_keepalive_connections=5,
            max_connections=10,
        ),
        timeout=httpx.Timeout(30.0, connect=5.0),
    ),
)


async def get_llm_response(messages: list[dict]) -> str:
    """Envía mensajes al LLM y devuelve la respuesta como texto (sin tools)."""
    response = await client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
    )
    return response.choices[0].message.content


async def get_llm_response_with_tools(
    messages: list[dict], tools: list[dict]
) -> ChatCompletionMessage:
    """Envía mensajes al LLM con tool definitions y devuelve el mensaje completo.

    El mensaje puede contener `content` (texto), `tool_calls` (llamadas a tools),
    o ambos. El caller debe inspeccionar el resultado para decidir qué hacer.
    """
    response = await client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
        tools=tools,
        tool_choice="auto",
    )
    return response.choices[0].message


async def stream_llm_response_with_tools(
    messages: list[dict], tools: list[dict]
):
    """Streaming: emite chunks a medida que llegan del LLM.

    Cada chunk es un dict:
      {"type": "token", "content": "Hola"}         → texto parcial
      {"type": "tool_call_delta", "index": 0, ...} → fragmento de tool call
      {"type": "done", "message": ChatCompletionMessage} → mensaje completo al final

    Usar como async generator:
        async for chunk in stream_llm_response_with_tools(messages, tools):
            if chunk["type"] == "token":
                await ui.stream_token(chunk["content"])
            elif chunk["type"] == "done":
                response_message = chunk["message"]
    """
    stream = await client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
        tools=tools,
        tool_choice="auto",
        stream=True,
    )

    tool_call_buffer: dict[int, dict] = {}  # index → {name, arguments}
    accumulated_content = ""

    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta is None:
            continue

        # Texto parcial
        if delta.content:
            accumulated_content += delta.content
            yield {"type": "token", "content": delta.content}

        # Tool calls (llegan como deltas incrementales)
        if delta.tool_calls:
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index
                if idx not in tool_call_buffer:
                    tool_call_buffer[idx] = {"name": "", "arguments": ""}
                if tc_delta.function:
                    if tc_delta.function.name:
                        tool_call_buffer[idx]["name"] = tc_delta.function.name
                        yield {
                            "type": "tool_call_delta",
                            "index": idx,
                            "name": tc_delta.function.name,
                            "arguments": "",
                        }
                    if tc_delta.function.arguments:
                        tool_call_buffer[idx]["arguments"] += tc_delta.function.arguments

        # Fin del stream
        finish_reason = chunk.choices[0].finish_reason if chunk.choices else None
        if finish_reason:
            # Reconstruir el mensaje completo (necesario para tool calling)
            tool_calls = None
            if tool_call_buffer:
                tool_calls = [
                    ChatCompletionMessageToolCall(
                        id=f"call_{idx}",
                        type="function",
                        function=Function(
                            name=buf["name"],
                            arguments=buf["arguments"],
                        ),
                    )
                    for idx, buf in sorted(tool_call_buffer.items())
                ]

            message = ChatCompletionMessage(
                content=accumulated_content or None,
                role="assistant",
                tool_calls=tool_calls,
            )
            yield {"type": "done", "message": message}
