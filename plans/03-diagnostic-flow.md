# Plan 3: Flujo de Diagnóstico Completo

> **Depende de:** Plan 2 (Persistencia)
> **Entrega:** Agente con tool calling, ~12 preguntas adaptativas, resumen estructurado, cierre automático

## Objetivo

Reemplazar la conversación libre actual por un flujo de diagnóstico estructurado pero conversacional. El agente guía al lead con preguntas adaptativas, usa herramientas para contar preguntas, buscar documentos relevantes, y registrar datos del lead. Al finalizar, genera un resumen y cierra la sesión.

---

## Lo que se arrastra del Plan 1 (temporal, a reemplazar)

En el Plan 1 dejamos un **parche temporal** en `src/agent/prompts.py` con una sección "Cierre de la conversación" que le pide al LLM cerrar después de 4-6 intercambios y hacer un resumen informal. Esto funciona pero es frágil:

- **No hay contador real**: el LLM "estima" cuántos intercambios pasaron, a veces se equivoca
- **No hay resumen estructurado**: el cierre es texto libre, no se persiste en `leads.resumen_diagnostico`
- **No se marca `completado` en DB**: el lead queda en estado `activo`
- **No hay validación**: si el usuario da info incompleta, igual cierra

Este Plan 3 **reemplaza completamente** ese parche por un mecanismo robusto con tool calling.

---

## Cambios en el system prompt

- **Eliminar** la sección "Cierre de la conversación" del prompt actual
- Agregar instrucciones detalladas para cada fase (ver abajo)
- El prompt debe incluir la lista completa de tools disponibles y cuándo usarlas

---

## Fases del diagnóstico

### Fase 0 — Identificación conversacional (2-3 preguntas)

De forma natural, sin parecer un formulario:
- Nombre
- Email ("por si se corta la charla")
- Empresa

Apenas obtiene cada dato → llama a `registrar_lead(nombre=..., email=..., empresa=...)`.

### Fase 1 — Diagnóstico (máx. 12 preguntas)

Dominios a explorar (orden flexible, adaptativo):
1. Perfil de la empresa (rubro, tamaño, estructura)
2. Casos de uso actuales de IA
3. Perfiles de usuarios que usan o usarían IA
4. Proveedores y herramientas actuales
5. Infraestructura de datos y base de conocimiento
6. Gobernanza y políticas de IA
7. Presupuesto y expectativas de ROI
8. Experiencias previas (qué funcionó, qué no)

Reglas:
- Máximo 12 preguntas de diagnóstico (excluyendo las 2-3 de identificación)
- Usar `contador_preguntas()` para saber cuántas quedan
- Si un dominio no aplica, saltearlo
- Cada 3-4 preguntas, hacer un micro-resumen de validación
- Al llegar a la pregunta 10, avisar que quedan pocas

---

## Tools

### `registrar_lead(nombre, email, empresa, cargo?)`
Actualiza los campos del lead en DB. Se llama incrementalmente (nombre primero, email después, etc.).

### `contador_preguntas()`
Devuelve cuántas preguntas de diagnóstico se hicieron ya y cuántas quedan. El agente usa esto para decidir si sigue preguntando o va cerrando.

### `buscar_documentos(query, tipo?)`
Busca en la base de conocimiento estática de Farox (archivos .md con info de genia.coop — ver Plan 9). El agente la usa si el lead menciona una tecnología o pregunta por capacidad técnica.

### `buscar_cv(tecnologia)`
Stub informativo. Farox no mantiene una base de CVs indexados. Si el lead pregunta "¿tienen a alguien que sepa X?", el agente deriva al equipo comercial.

### `generar_resumen()`
La usa el agente al finalizar. Genera un resumen estructurado del diagnóstico y:
1. Lo guarda en `leads.resumen_diagnostico`
2. Cambia `leads.estado` a `completado`
3. Devuelve el texto para mostrarlo al lead

---

## Tool calling loop

El loop actual en `conversation.py` usa `get_llm_response()` que solo devuelve texto. Hay que reemplazarlo por un loop que soporte tool calling:

1. Enviar messages al LLM con las tool definitions
2. Si el LLM responde con `tool_calls` → ejecutar la tool → devolver resultado al LLM → repetir
3. Si el LLM responde con texto → devolver al usuario

---

## Archivos a modificar / crear

| Archivo | Acción |
|---------|--------|
| `src/agent/prompts.py` | **Reemplazar** system prompt completo. Eliminar sección "Cierre" temporal. |
| `src/agent/tools.py` | **Nuevo**. Definiciones de tools en formato OpenAI/Anthropic. |
| `src/agent/tool_handlers.py` | **Nuevo**. Implementación de cada tool (usa queries del Plan 2). |
| `src/agent/conversation.py` | **Refactorizar**. Loop con tool calling en vez de `get_llm_response()`. |
| `src/chainlit/hooks.py` | Ajustar `on_message` para llamar al nuevo loop con tool calling. |

> **Nota:** Los modelos y queries ya están completos gracias al Plan 2. Plan 3 solo los consume (`update_lead`, `count_questions`, `save_interaction`, etc.).

---

## Verificación

1. Iniciar chat → el agente pide nombre, email, empresa de forma natural
2. Los datos se persisten incrementalmente en `leads`
3. `contador_preguntas()` funciona y el agente ajusta su comportamiento
4. Al llegar al límite → resumen estructurado automático
5. El lead queda en estado `completado` con `resumen_diagnostico` poblado
6. Si el lead menciona una tecnología → el agente busca en la base de conocimiento (archivos .md, Plan 9)
