# Plan 4 — Diagnóstico de charla real y mejoras conversacionales

**Fecha:** 2026-07-20
**Lead analizado:** Peter (peter@mail.com, "Peter te Nutre")
**Total de interacciones:** 34 registros en DB

---

## 1. La charla — resumen cronométrico

Charla completa entre las 17:59:35 y 18:04:33 (~5 minutos). Se hicieron 10 preguntas de
diagnóstico de un máximo de 12. El lead venía con una necesidad clara y bien definida desde
el primer mensaje.

| # | Tipo | Latencia (user→resp) | Tools llamadas |
|---|------|----------------------|----------------|
| 1 | Presentación inicial | ~3.5s | — |
| 2 | Pide nombre | ~4.3s | `registrar_lead` |
| 3 | Pide mail + empresa | ~5.7s | `registrar_lead` + `contador_preguntas` |
| 4 | Pregunta volumen semanal | ~4.1s | — |
| 5 | Pregunta cómo maneja consultas | ~5.9s | `registrar_lead` + `contador_preguntas` |
| 6 | Pregunta tipo de videollamada | ~9.6s | `registrar_lead` + `contador_preguntas` |
| 7 | Pregunta herramientas actuales | ~6.8s | `contador_preguntas` |
| 8 | Pregunta sobre la app existente | ~8.0s | `contador_preguntas` |
| 9 | Pregunta presupuesto | ~6.0s | `contador_preguntas` |
| 10 | Pregunta panel de pacientes | ~10.0s | `generar_resumen` + resumen final |

**Latencia promedio por respuesta:** ~6.4 segundos
**Latencia sin tools:** ~3.8 segundos
**Latencia con tools (2 LLM calls):** ~7.1 segundos

---

## 2. Diagnóstico de los puntos señalados

### 2.1 Preguntas repetitivas / sensación de que "ya se había consultado"

**Hallazgo: el problema no es que repita preguntas al usuario, sino que repite tool calls
innecesarias que no aportan nada.** Esto dilata cada turno y puede dar la sensación de que
el agente "no se acuerda" de lo que ya sabe.

**Evidencia concreta de la DB:**

| Interacción | ¿Había datos nuevos? | `registrar_lead` llamado |
|-------------|---------------------|--------------------------|
| "unas 20 por semana" (#9) | No | ✅ — actualiza nombre, email, empresa (mismos datos) |
| "es una charla gratuita..." (#15) | No | ✅ — actualiza nombre, email, empresa (mismos datos) |
| "si, uso whatsapp business..." (#19) | No | ✅ — actualiza nombre, email, empresa (mismos datos) |

**Causa raíz:** El system prompt instruye al LLM a llamar `registrar_lead` "apenas obtengas
cada dato" y "no esperes a juntar todo". El LLM interpreta esto como "llámala siempre",
incluso cuando el mensaje del usuario no contiene ningún dato de identificación nuevo.
El tool handler además reporta `"updated": ["nombre", "email", "empresa"]` aunque los
valores sean idénticos a los ya persistidos (no hay lógica de detección de cambios reales —
esto se ataca en el Plan 5).

**Costo:** 3 llamadas innecesarias a `registrar_lead` → 3 round-trips extra al LLM →
~4-6 segundos acumulados de latencia innecesaria.

### 2.2 Proceso de preguntas sentido como "largo"

**Causas identificadas:**

1. **Latencia acumulada (causa principal).** Con ~6.4s promedio por respuesta, 10 turnos
   suman más de un minuto de espera pura. La percepción de "largo" está directamente ligada
   a la latencia, no a la cantidad de preguntas (10 de 12 no es excesivo). Las mejoras de
   latencia y streaming se abordan en el **Plan 5**.

2. **Preguntas compuestas que violan el prompt.** El system prompt dice "una pregunta por
   vez", pero el agente hace preguntas múltiples:
   - Turno #3: "¿me pasás tu mail? Y también, ¿cómo se llama tu consultorio?" (2 preguntas)
   - Turno #5: "¿WhatsApp Business? ¿Instagram empresa? ¿CRM o planilla?" (3 sub-preguntas)
   - Turno #8: "¿registra datos estructurados? ¿Firebase o teléfono?" (2 preguntas)

   Esto es inconsistente: a veces el agente respeta la regla, a veces no. El LLM
   (deepseek-v4-flash) parece tener dificultad siguiendo esta instrucción de forma
   consistente.

3. **Micro-resúmenes de validación casi ausentes.** El prompt pide "cada 3-4 preguntas,
   hacé un micro-resumen de validación". Solo ocurrió una vez (turno #8: "Bien, ya llevamos
   varias preguntas, vamos bien"), pero fue más un anuncio de avance que un resumen de
   validación real ("Entonces hasta ahora entiendo que...").

4. **El `contador_preguntas` se llama pero su resultado se desaprovecha.** De 6 llamadas
   al contador, solo en 2 el asistente usó el dato para regular el ritmo. Las otras 4 veces
   el contador se llamó "por las dudas" pero su resultado fue ignorado en la respuesta.
   Esto se mitiga desde el prompt (este plan) y desde el código (Plan 5).

### 2.3 Lentitud de respuestas (3-5 segundos)

**Diagnóstico completo en el Plan 5.** En resumen: el bottleneck es el modelo LLM (~3.5s
base), agravado por tool calls redundantes que duplican cada turno, y ausencia de streaming
que hace que la espera se sienta peor.

---

## 3. Hallazgos adicionales detectados

### 3.1 El asistente se presentó dos veces

El prompt dice "Ya te presentaste. No vuelvas a presentarte". Sin embargo, en el saludo
inicial (`GREETING`) y en la primera respuesta el tono es de presentación ("Soy el consultor
de IA de GenIA"), y luego en el mensaje #2 vuelve a usar un tono de bienvenida. Es sutil
pero contribuye a la sensación de "arranque lento".

### 3.2 `pregunta_numero` en la tabla `interacciones` no se está usando

El campo `pregunta_numero` existe en el modelo ([models.py:64](src/db/models.py#L64)) pero
nunca se persiste con un valor — siempre queda `NULL`. El contador de preguntas actual
(`count_questions`) usa un `COUNT` de mensajes `assistant` como proxy
([queries.py:68-76](src/db/queries.py#L68-L76)), lo cual es frágil: cuenta tool_calls de
asistente si tuvieran ese rol, y no distingue entre una pregunta real y un comentario del
asistente.

### 3.3 DeepSeek Flash no sigue consistentemente instrucciones de "una pregunta por vez"

En 3 de 10 turnos el agente hizo preguntas compuestas. Esto es un problema de capacidad del
modelo (`deepseek-v4-flash`) para seguir instrucciones de formato conversacional con
precisión. Modelos más grandes (Sonnet, Opus, GPT-4) suelen respetar mejor este tipo de
reglas. Cambiar a un modelo más capaz podría resolverlo sin cambios de prompt — ver
benchmark de modelos en Plan 5.

### 3.4 El historial entre turnos no incluye contexto de tool calls previas

[hooks.py:49-55](src/chainlit/hooks.py#L49-L55) — después de `process_message`, el
historial de Chainlit solo recibe `{"role": "assistant", "content": response}`. Las tool
calls que ocurrieron durante `process_message` no se preservan entre turnos. Esto significa
que en el siguiente turno el LLM no "recuerda" haber llamado al contador o al
registrar_lead. Esto podría contribuir a las llamadas redundantes.

---

## 4. Mejoras de este plan (conversacionales / de prompt)

Las mejoras de latencia, streaming y performance se movieron al **Plan 5**.
Este plan se enfoca en cambios de prompt y lógica conversacional para mejorar la calidad
del diálogo.

### Mejora 4A — Prompt: no llamar `registrar_lead` sin datos nuevos

**Problema:** El prompt actual dice "llamala apenas obtengas cada dato", y el LLM lo
interpreta como "llámala siempre". En 3 de 10 turnos se llamó sin que hubiera datos de
identificación nuevos.

**Cambio en el prompt** (sección `registrar_lead`):

```diff
- Llamala **apenas obtengas cada dato**. Si el lead te dice el nombre, llamala ya solo
- con nombre. Si después te da el email, llamala de nuevo solo con email. No esperes a
- juntar todo.

+ Llamala **solo cuando el lead te dé un dato de identificación NUEVO** (nombre, email,
+ empresa, cargo). Si el lead habla de otra cosa (volumen de consultas, herramientas,
+ presupuesto), NO la llames — no hay nada nuevo que registrar.
+
+ Ejemplos:
+ - Lead dice "soy Juan" → llamala con nombre="Juan"
+ - Lead dice "uso WhatsApp Business" → NO la llames (no es un dato de identificación)
+ - Lead dice "mi mail es juan@acme.com" → llamala con email="juan@acme.com"
```

### Mejora 4B — Prompt: reforzar "una pregunta por vez"

**Problema:** En 3 de 10 turnos el agente hizo 2 o más preguntas juntas. La instrucción
actual ("hacé preguntas de a una") no es suficiente para DeepSeek Flash.

**Cambio en el prompt** (sección "Fase 0 — Identificación conversacional"):

Agregar ejemplos explícitos de lo que NO hacer:

```
Regla: **una pregunta por vez, siempre**. Ejemplos de lo que NO hacer:

  ❌ MAL: "¿Me pasás tu mail? Y también, ¿cómo se llama tu consultorio?"
  ✅ BIEN: "¿Me pasás tu mail por si se corta la charla?"
     (esperás la respuesta, y recién después preguntás por la empresa)

  ❌ MAL: "¿Usás WhatsApp Business? ¿Y tenés CRM o planilla?"
  ✅ BIEN: "¿Usás WhatsApp Business o alguna herramienta para manejar consultas?"

Si necesitás preguntar dos cosas, elegí la más importante y dejá la otra para el
siguiente turno. Esto hace que la conversación sea más natural y menos interrogatorio.
```

Agregar al final del prompt, como recordatorio:

```
⚠️  IMPORTANTE — Reglas de formato:
- NUNCA hagas más de una pregunta en el mismo mensaje.
- NUNCA llames a registrar_lead si el usuario no dio datos de identificación nuevos.
- Cada 3-4 preguntas de diagnóstico, hacé una pausa para validar lo entendido.
```

### Mejora 4C — Prompt: micro-resúmenes de validación con template concreto

**Problema:** El prompt pide micro-resúmenes cada 3-4 preguntas pero nunca se cumplieron.
La instrucción actual es vaga ("hacé un micro-resumen de validación").

**Cambio en el prompt** (reemplazar la regla actual en "Reglas del diagnóstico"):

```diff
- **Cada 3-4 preguntas**, hacé un micro-resumen de validación ("Entonces hasta ahora
- entiendo que...").

+ **Cada 3-4 preguntas**, hacé una pausa de validación con este formato exacto:
+
+   "Hasta ahora entiendo que [resumen de 1-2 líneas de lo que me contaste].
+   ¿Voy bien encaminado?"
+
+ Esto genera confianza, permite que el lead te corrija si interpretaste algo mal,
+ y rompe la monotonía del ping-pong pregunta-respuesta. Usá el contador_preguntas()
+ para saber cuándo hacer esta pausa (preguntas 3, 6 y 9).
```

### Mejora 4D — Aprovechar `pregunta_numero` en la tabla

**Problema:** El campo `pregunta_numero` en `interacciones` nunca se persiste. El contador
actual usa `COUNT` de mensajes `assistant` como proxy, que es frágil.

**Cambio en el código:** En [hooks.py](src/chainlit/hooks.py), al guardar la interacción
del asistente, calcular y persistir `pregunta_numero`. El cálculo es simple: contar
cuántas interacciones `assistant` tiene ya el lead + 1. Esto:

- Hace que el contador sea preciso y auditizable
- Permite queries más ricas ("¿en qué pregunta abandonan más los leads?")
- No depende de un COUNT que puede incluir tool_calls u otros mensajes

---

## 5. Resumen de prioridades — Plan 4

| # | Mejora | Tipo | Impacto | Esfuerzo |
|---|--------|------|---------|----------|
| 4A | Prompt: no llamar `registrar_lead` sin datos nuevos | Prompt | ALTO | Bajo |
| 4B | Prompt: reforzar "una pregunta por vez" con ejemplos | Prompt | MEDIO | Bajo |
| 4C | Prompt: micro-resúmenes con template concreto | Prompt | MEDIO | Bajo |
| 4D | Persistir `pregunta_numero` en interacciones | Código | BAJO | Bajo |

Todas son cambios acotados. Las mejoras de latencia, streaming y performance están en el
**Plan 5**.
