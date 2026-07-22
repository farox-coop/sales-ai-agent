# Plan 5 — Streaming, latencia y optimización de UX

**Fecha:** 2026-07-20
**Depende de:** Plan 4 (mejoras conversacionales)
**Objetivo:** Reducir la latencia percibida y real del agente, mejorando la experiencia
del lead sin cambiar la lógica de negocio.

---

## 1. Diagnóstico de latencia actual

De la charla con Peter (34 interacciones, 10 turnos):

| Métrica | Valor |
|---------|-------|
| Latencia promedio por turno | ~6.4s |
| Latencia sin tools (solo texto) | ~3.8s |
| Latencia con tools (2 llamadas LLM) | ~7.1s |
| Llamadas totales al LLM en la charla | ~16 (10 respuestas + ~6 tools post-proceso) |
| Tool calls innecesarias | 3 de 10 turnos (30%) |
| Tiempo total acumulado de espera | ~65 segundos |

**Causas raíz de la latencia:**

1. **Modelo lento** — `deepseek-v4-flash` tarda ~3.5s por llamada incluso sin tools
2. **Doble llamada al LLM por turno con tools** — cada tool call agrega un round-trip
   completo (LLM decide → tools ejecutan → LLM genera respuesta final)
3. **Tool calls innecesarias** — `registrar_lead` y `contador_preguntas` se llaman "por
   las dudas" sin aportar valor
4. **Sin streaming** — el usuario no ve nada hasta que la respuesta completa está generada
5. **Tool calls secuenciales** — cuando hay 2+ tools independientes, se ejecutan una
   después de otra en vez de en paralelo

---

## 2. Mejora 5A — Streaming de respuestas del LLM

**Impacto:** ALTO (reduce latencia percibida a ~1s para time-to-first-token)
**Esfuerzo:** Medio
**Archivos:** [src/llm/client.py](src/llm/client.py), [src/chainlit/hooks.py](src/chainlit/hooks.py),
[src/agent/conversation.py](src/agent/conversation.py)

### 2.1 Situación actual

```python
# client.py — sin streaming
response = await client.chat.completions.create(
    model=settings.llm_model,
    messages=messages,
    max_tokens=settings.llm_max_tokens,
    temperature=settings.llm_temperature,
    tools=tools,
    tool_choice="auto",
)
return response.choices[0].message  # mensaje completo de una vez
```

El usuario espera 3-7 segundos sin ver nada en pantalla. La respuesta aparece completa
de golpe.

### 2.2 Qué cambiar

#### Paso 1 — Nuevo método con streaming en `client.py`

```python
async def stream_llm_response_with_tools(
    messages: list[dict], tools: list[dict]
) -> AsyncGenerator[dict, None]:
    """Streaming: emite chunks a medida que llegan.

    Cada chunk es:
      {"type": "token", "content": "Hola"}  → texto parcial
      {"type": "tool_call_delta", "index": 0, "name": "...", "arguments": "..."}
      {"type": "done", "message": ChatCompletionMessage}  → mensaje completo al final
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

    async for chunk in stream:
        delta = chunk.choices[0].delta

        # Texto
        if delta.content:
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
                        yield {"type": "tool_call_delta", "index": idx,
                               "name": tc_delta.function.name, "arguments": ""}
                    if tc_delta.function.arguments:
                        tool_call_buffer[idx]["arguments"] += tc_delta.function.arguments

        # Fin del stream
        if chunk.choices[0].finish_reason:
            # Reconstruir el mensaje completo (necesario para tool calling)
            from openai.types.chat import ChatCompletionMessage
            from openai.types.chat.chat_completion_message_tool_call import (
                ChatCompletionMessageToolCall,
                Function,
            )

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
                content="".join(...),  # acumulado durante el stream
                role="assistant",
                tool_calls=tool_calls,
            )
            yield {"type": "done", "message": message}
```

#### Paso 2 — Modificar `process_message` para soportar streaming

El loop de tool calling en [conversation.py](src/agent/conversation.py) necesita dos modos:

1. **Modo streaming (default):** cuando el LLM genera texto sin tool calls → streamea al
   frontend
2. **Modo interno:** cuando el LLM decide tool calls → no hay texto que mostrar, procesa
   las tools y repite

```python
async def process_message_streaming(
    user_message: str,
    history: list[dict],
    db: AsyncSession,
    lead_id: uuid.UUID,
    stream_callback: Callable[[str], Awaitable[None]],  # para mandar tokens al frontend
) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_message},
    ]

    accumulated_content = ""

    for _ in range(MAX_TOOL_ROUNDS):
        full_content = ""
        tool_call_buffer = {}

        async for chunk in stream_llm_response_with_tools(messages, TOOLS):
            if chunk["type"] == "token":
                full_content += chunk["content"]
                await stream_callback(chunk["content"])  # ← va al frontend en vivo

            elif chunk["type"] == "done":
                response_message = chunk["message"]

        # Si hay tool_calls → procesar sin mostrar nada al usuario (o mostrar
        # un indicador sutil)
        if response_message.tool_calls:
            # Guardar en messages, ejecutar tools, seguir loop
            ...
            continue

        # Sin tool_calls → el texto ya se streameó, devolverlo
        return full_content or response_message.content or ""
```

#### Paso 3 — Modificar `hooks.py` para usar streaming

```python
@cl.on_message
async def on_message(message: cl.Message):
    # ... setup ...
    msg = cl.Message(content="")
    await msg.send()  # mensaje vacío, se llenará incrementalmente

    async def stream_token(token: str):
        await msg.stream_token(token)

    response = await process_message_streaming(
        message.content, history, db, lead_id, stream_callback=stream_token
    )

    await msg.update()  # finaliza el mensaje
```

### 2.3 Riesgos

- **El endpoint `genway.farox.coop` debe soportar SSE (Server-Sent Events).** La API de
  OpenAI usa `stream=True` → SSE. Si el proxy no lo pasa correctamente, falla.
  **Mitigación:** hacer una prueba rápida con `curl` antes de implementar.
- **Tool calls con streaming son más complejos.** Los tool call deltas llegan en chunks
  separados y hay que acumularlos. La implementación de arriba lo contempla.
- **Si el LLM genera texto Y tool_calls en el mismo mensaje**, ¿mostramos el texto o
  esperamos? La respuesta: si el contenido es introductorio ("Déjame buscar eso..."),
  mostrarlo es buena UX. Si son tool_calls sin texto, no hay nada que mostrar.

---

## 3. Mejora 5B — Eliminar tool calls redundantes desde el código

**Impacto:** ALTO (ahorra 3-6s por charla, reduce writes innecesarios a DB)
**Esfuerzo:** Bajo
**Archivo:** [src/agent/tool_handlers.py](src/agent/tool_handlers.py)

### 3.1 Situación actual

`handle_registrar_lead` (líneas 50-68) siempre hace `update_lead()` y reporta los campos
como actualizados, sin verificar si el valor realmente cambió:

```python
async def handle_registrar_lead(db, lead_id, args):
    updates = {}
    for field in ("nombre", "email", "empresa", "cargo"):
        value = args.get(field)
        if value and value.strip():
            updates[field] = value.strip()

    await update_lead(db, lead_id, **updates)  # siempre UPDATE aunque no cambió nada
    return {"status": "ok", "updated": list(updates.keys()), ...}
```

### 3.2 Qué cambiar

```python
async def handle_registrar_lead(db, lead_id, args):
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
            unchanged.append(field)  # ya tiene este valor
        else:
            updates[field] = value

    if not updates:
        return {
            "status": "ok",
            "updated": [],
            "unchanged": unchanged,
            "msg": "Sin datos nuevos para registrar (todos los campos ya tenían "
                   f"el valor proporcionado).",
        }

    await update_lead(db, lead_id, **updates)
    return {
        "status": "ok",
        "updated": list(updates.keys()),
        "unchanged": unchanged,
        "msg": f"Datos actualizados: {', '.join(updates.keys())}. "
               f"Sin cambios: {', '.join(unchanged)}." if unchanged else "",
    }
```

### 3.3 Efecto en el LLM

Cuando el LLM llame a `registrar_lead` sin datos nuevos, el tool result será:
```json
{"status": "ok", "updated": [], "unchanged": ["nombre", "email", "empresa"],
 "msg": "Sin datos nuevos para registrar."}
```

El LLM aprende que no necesita llamar a esta tool si no hay datos nuevos — el feedback
es claro e inmediato.

### 3.4 Cambio complementario en tool description (post-implementación)

La descripción de `registrar_lead` en [tools.py](src/agent/tools.py) se ajustó para
desincentivar llamadas innecesarias desde el prompt. La versión original alentaba
llamar "NI BIEN obtengas cada dato" y "apenas el lead te dice su nombre, llamala solo
con nombre". La nueva descripción indica:

> Llamala SOLO cuando el lead proporcione un dato NUEVO que no hayas registrado antes.
> No la llames por las dudas o 'para verificar': la tool te informa si los datos ya
> estaban registrados y no hubo cambios.

Esto ataca la causa raíz: el LLM llamaba `registrar_lead` en 9 de 13 turnos (69%),
cuando solo 4 tenían datos nuevos. Combinado con el cambio en el handler (3.2), la
reducción de tool calls innecesarias debería ser cercana al 100%.

---

## 4. Mejora 5D — Indicador visual de typing + acuse instantáneo

**Impacto:** MEDIO (reduce ansiedad del usuario durante la espera)
**Esfuerzo:** Bajo
**Archivo:** [src/chainlit/hooks.py](src/chainlit/hooks.py)

### 4.1 Qué cambiar

```python
@cl.on_message
async def on_message(message: cl.Message):
    # ... setup, guardar mensaje del usuario ...

    # Acuse instantáneo (no llama al LLM, es un mensaje fijo)
    # Solo se muestra si la respuesta real va a tardar
    # Opción A: mensaje de "typing" que se actualiza
    msg = cl.Message(content="")  # espacio para streaming

    # Opción B: indicador de typing nativo de Chainlit
    # Chainlit ya soporta esto con msg.stream_token()
    await msg.send()

    # El streaming se encarga del resto — tokens aparecen en vivo
    async def stream_token(token: str):
        await msg.stream_token(token)

    response = await process_message_streaming(
        message.content, history, db, lead_id, stream_callback=stream_token
    )

    await msg.update()
```

Con streaming (5A), el usuario ve el primer token en ~1s, lo cual ya funciona como
"acuse de recibo" natural. El indicador de typing se vuelve menos necesario pero
sigue sumando para los casos donde el LLM está decidiendo tool calls (sin texto que
mostrar durante ~3s).

### 4.2 Alternativa: skeleton/placeholder durante tool execution

Si el LLM decide tool calls, en vez de pantalla en blanco, mostrar un placeholder:

```
🔍 Analizando tu respuesta...
```

Y cuando las tools terminan, el placeholder se reemplaza con la respuesta real. Esto
cubre el "valle" de 2-4s donde el LLM está procesando tools y no hay texto que streamear.

---

## 5. Mejora 5E — Paralelizar tool calls independientes ~~(DESCARTADA)~~

**Impacto:** ~~MEDIO~~ **DESCARTADA**
**Esfuerzo:** ~~Medio~~
**Motivo del descarte:** `AsyncSession` de SQLAlchemy no soporta operaciones
concurrentes sobre la misma sesión. Al ejecutar `asyncio.gather()` con múltiples
`save_interaction()` en paralelo, la sesión entra en estado inconsistente:

```
sqlalchemy.exc.InvalidRequestError: This session is provisioning a new connection;
concurrent operations are not permitted
```

El ahorro real era mínimo (~50ms por tool) porque las tools son queries SQL rápidas.
No justificaba la complejidad ni el riesgo. Las tools se ejecutan secuencialmente.

---

## 6. Mejora 5F — Connection pooling y optimizaciones HTTP

**Impacto:** BAJO (ahorro de ~50-200ms por llamada)
**Esfuerzo:** Bajo
**Archivo:** [src/llm/client.py](src/llm/client.py)

### 6.1 Qué cambiar

El cliente OpenAI usa `httpx` internamente. Asegurar que:

```python
from openai import AsyncOpenAI

client = AsyncOpenAI(
    api_key=settings.llm_api_key,
    base_url=settings.llm_base_url,
    timeout=30.0,                   # timeout explícito
    max_retries=2,                  # reintentos con backoff
    http_client=httpx.AsyncClient(  # cliente HTTP compartido
        limits=httpx.Limits(
            max_keepalive_connections=5,
            max_connections=10,
        ),
        timeout=httpx.Timeout(30.0, connect=5.0),
    ),
)
```

Esto asegura que las conexiones TCP/TLS se reusan entre llamadas, evitando el handshake
en cada request.

> **Nota sobre `max_tokens`:** Se evaluó reducir `max_tokens` contextualmente (de 4096
> a 1024 para respuestas y 256 para tool results), pero se descartó porque:
> - `max_tokens` es un techo, no un target — el modelo genera los mismos tokens con
>   límite 1024 o 4096; la latencia es idéntica.
> - El cierre de diagnóstico del agente puede ser extenso (resumen de toda la
>   conversación) y 1024 tokens es un techo riesgoso.
> - No hay evidencia de que los modelos actuales "rellenen" hasta el límite.

---

## 7. Mejora 5G — Respuesta directa para mensajes triviales

**Impacto:** BAJO (evita 1-2 llamadas al LLM por charla)
**Esfuerzo:** Bajo
**Archivo:** [src/chainlit/hooks.py](src/chainlit/hooks.py)

### 7.1 Qué cambiar

Si el usuario manda "gracias", "bueno" en los primeros mensajes (antes de que arranque
el diagnóstico real), no tiene sentido pasar por el loop de tool calling completo.

```python
# En on_message, antes de process_message
TRIVIAL_RESPONSES: dict[str, str] = {
    "gracias": "¡De nada! ¿Hay algo más en lo que pueda ayudarte?",
    "muchas gracias": "¡De nada! ¿Hay algo más en lo que pueda ayudarte?",
    "bueno": "¿Hay algo más que quieras profundizar?",
}

normalized = message.content.strip().lower()
conversation_started = len(history) > 1  # más que solo el greeting inicial
if normalized in TRIVIAL_RESPONSES and not conversation_started:
    response = TRIVIAL_RESPONSES[normalized]
    await save_interaction(db, lead_id, MessageRole.assistant, response)
    await cl.Message(content=response).send()
    return
```

### 7.2 Restricciones importantes (agregadas post-implementación)

1. **Solo aplica cuando no hay conversación iniciada** (`len(history) <= 1`, es decir,
   solo el saludo inicial). Si ya hubo al menos un intercambio user-assistant, el LLM
   maneja el mensaje — incluso "gracias" puede ser una respuesta a un resumen del agente.

2. **`"si"` fue removido explícitamente** — es la palabra más dependiente de contexto
   en español. Causó un descarrilamiento en la prueba con Peter: el agente preguntó
   "¿Voy bien encaminado?", Peter respondió "sí", y el fast-path devolvió un
   "¿En qué te gustaría profundizar?" que rompió el hilo de la conversación.

3. **`"ok"`, `"dale"`, `"perfecto"`, `"bien"` también fueron removidos** — en medio
   de un diagnóstico, todos pueden ser confirmaciones a preguntas del agente, no
   mensajes vacíos.

---

## 8. Resumen de prioridades — Plan 5

| # | Mejora | Impacto | Esfuerzo | Ahorro estimado |
|---|--------|---------|----------|-----------------|
| 5A | Streaming de respuestas | ALTO | Medio | TTFT de 6s → ~1s (perceptual) |
| 5B | Tool calls sin cambios detectados | ALTO | Bajo | 3-6s menos por charla |
| 5D | Indicador visual + skeleton tool exec | MEDIO | Bajo | Mejor percepción en "valles" sin texto |
| 5G | Fast-path para mensajes triviales | BAJO | Bajo | 3.5s por mensaje trivial |
| 5F | Connection pooling HTTP | BAJO | Bajo | 50-200ms por llamada |
| ~~5E~~ | ~~Paralelizar tool calls~~ | ~~DESCARTADA~~ | — | AsyncSession no soporta concurrencia |

### Orden de implementación real

```
5B → 5A → 5D → 5G → 5F
(5E descartada — AsyncSession no es concurrency-safe)
```

**5B primero** porque es el cambio más simple y de mayor impacto relativo al esfuerzo
(cambiar un handler). **5A segundo** porque requiere más código pero transforma la
experiencia del lead. El resto son mejoras incrementales.

> **Nota:** La selección de modelo LLM (antes 5C) se movió al Plan 6 (ahora deprecado — no es prioridad hacer un benchmark formal).
> benchmark de modelos se hará exclusivamente contra el gateway `genway.farox.coop` con
> los modelos disponibles en ese contexto.

---

## 9. Métricas de éxito

Después de implementar, medir contra la misma charla de Peter (o una similar):

| Métrica | Actual | Objetivo |
|---------|--------|----------|
| Time-to-first-token | ~3.5s | < 1.5s |
| Latencia total por turno | ~6.4s | < 3s |
| Tool calls innecesarias por charla | 3 | 0 |
| Turnos con preguntas compuestas | 3/10 | 0/10 |
| Percepción del lead | "lento" | "fluido" |

---

## 10. Correcciones post-implementación (2026-07-20)

Después de probar con una charla real (Peter, 13 turnos), se detectaron y corrigieron
tres problemas:

### 10.1 Fast-path 5G demasiado agresivo

**Problema:** El fast-path matcheaba `"si"` en medio de un diagnóstico. El agente
preguntó "¿Voy bien encaminado?", Peter respondió "sí" (confirmando), y el fast-path
devolvió "¿En qué te gustaría profundizar?". El lead quedó descolocado ("no entiendo")
y la conversación se descarriló por 2 turnos.

**Corrección:**
- `"si"` removido de `TRIVIAL_RESPONSES` — es la palabra más dependiente de contexto
- También removidos `"ok"`, `"dale"`, `"perfecto"`, `"bien"` — todos pueden ser
  confirmaciones a preguntas del agente en medio del diagnóstico
- Agregada guarda `len(history) > 1`: el fast-path solo aplica cuando la conversación
  no arrancó realmente (solo está el saludo inicial). Si ya hubo al menos un intercambio
  user-assistant, el LLM maneja el mensaje

### 10.2 registrar_lead llamado en el 69% de los turnos

**Problema:** De 13 turnos, 9 tenían `registrar_lead`. Después del turno 4 ya estaban
nombre, email y empresa. Las 6 llamadas siguientes fueron innecesarias — el LLM perdía
un round-trip completo (~3-4s) en cada una.

**Corrección:** La descripción de la tool en [tools.py](src/agent/tools.py) se reescribió
para decir "SOLO cuando el lead proporcione un dato NUEVO" en vez de "NI BIEN obtengas
cada dato". Esto complementa el cambio en el handler (5B) que ya detecta campos sin cambio.

### 10.3 Alucinación sobre error en el email

**Problema:** Turno 4: el agente dijo "Veo que tuviste un pequeño error en el mail
(repetiste la primera parte)". El lead escribió solo `peter@mail.com` — no hubo error.
Es una alucinación menor del LLM, no relacionada con los cambios de este plan.

**Conclusión:** No se modificó nada por esto — es un problema del modelo, no del código.
Si se vuelve recurrente, evaluar cambio de modelo (cambiando LLM_MODEL en .env).

### 10.4 Fase 0 del prompt demasiado lenta (3 turnos para datos de registro)

**Problema:** En la segunda charla con Peter, los primeros 4 turnos del agente incluyeron
3 dedicados exclusivamente a obtener nombre, email y empresa (~37 segundos de ida y vuelta
antes de la primera pregunta de diagnóstico). El prompt original exigía "una pregunta por
vez, siempre" incluso para datos de registro básicos, y pedía el email "por si se corta la
charla".

**Corrección en [prompts.py](src/agent/prompts.py):**

1. **Fase 0 reducida a 1-2 turnos máximo.** Nombre y empresa se pueden preguntar juntos:
   "¿Con quién tengo el gusto de hablar y cómo se llama tu emprendimiento?"

2. **Email movido al cierre.** En vez de pedirlo al principio "por si se corta", se pide
   al final como parte natural del cierre: "¿A qué mail te mando el resumen o la propuesta?"
   Esto además le da un propósito concreto al email.

3. **Regla "una pregunta por vez" relajada para Fase 0.** Esa regla aplica a las preguntas
   de diagnóstico (Fase 1), que requieren respuestas elaboradas. Para datos de registro,
   agrupar es más eficiente y menos "formulario".
