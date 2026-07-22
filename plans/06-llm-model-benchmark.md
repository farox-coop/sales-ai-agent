# Plan 6 — Benchmark y selección de modelo LLM ⚠️ DEPRECADO

> **Estado:** DEPRECADO (julio 2026).
>
> **Motivo:** El esfuerzo de hacer un benchmark formal de modelos no es prioridad ahora.
> El agente funciona aceptablemente con el modelo actual y el foco está en mejorar la
> experiencia conversacional (prompts, flujo, conocimiento).
>
> **Futuro:** Si la latencia o calidad del modelo actual se vuelven un problema medible,
> este plan se puede reactivar. Por ahora, cambiar de modelo es un cambio de variable
> de entorno (`LLM_MODEL`).

**Fecha:** 2026-07-20
**Depende de:** Plan 5 (streaming y optimización de UX)
**Objetivo:** Identificar el mejor modelo LLM disponible en el gateway `genway.farox.coop`
para el caso de uso del agente de ventas, balanceando latencia, calidad de tool calling y
naturalidad del español rioplatense.

---

## 1. Contexto

### 1.1 Restricción de infraestructura

**Todo el tráfico LLM debe pasar por el gateway `genway.farox.coop`.** No está permitido
usar LLMs por fuera de este gateway (nada de APIs directas a DeepSeek, Anthropic, OpenAI,
Fireworks, Together, etc.).

### 1.2 Modelos disponibles en el gateway

Estos son los modelos que podemos considerar para el benchmark:

| # | Modelo | Tipo | Notas |
|---|--------|------|-------|
| 1 | `deepseek-v4-flash` | Flash | **Baseline actual.** ~3.5s por llamada |
| 2 | `deepseek-v4-pro` | Pro | Mayor calidad, posiblemente más lento |
| 3 | `gpt-5.4-nano` | Nano | Modelo más chico de OpenAI, probablemente rápido |
| 4 | `gemini/gemini-3.1-flash-lite` | Flash-lite | Google, optimizado para latencia |
| 5 | `gemini/gemini-2.5-flash` | Flash | Google, generación anterior |
| 6 | `gpt-5.4-mini` | Mini | OpenAI, balance velocidad/calidad |
| 7 | `claude-haiku-4-5` | Haiku | Anthropic, tool use nativo |

---

## 2. Hipótesis

`deepseek-v4-flash` tarda ~3.5s por llamada simple. Esto es alto para un modelo "flash".
El objetivo del benchmark es determinar si hay un modelo en el gateway que ofrezca mejor
combinación de:

1. **Latencia** — TTFT más bajo
2. **Tool calling confiable** — que llame a `registrar_lead` solo cuando corresponde, sin
   llamadas redundantes
3. **Seguimiento de instrucciones** — "una pregunta por vez", tono conversacional
4. **Español rioplatense natural** — no neutro genérico

---

## 3. Metodología de benchmark

### 3.1 Script de prueba

Crear `scripts/benchmark_models.py` que automatice las pruebas contra el gateway.

### 3.2 Casos de prueba

Usar la conversación real de Peter como referencia. Preparar 4 escenarios:

| Escenario | Descripción | Qué mide |
|-----------|-------------|----------|
| A | Primer mensaje: "Hola, me llamo Peter y tengo un problema con mi inventario" | TTFT, calidad de tool calling (`registrar_lead`), tono de respuesta, ¿una sola pregunta? |
| B | Respuesta a pregunta del agente: "Vendo electrodomésticos, tengo 3 sucursales" | Fluidez de conversación, ¿registra datos nuevos? |
| C | Mensaje ambiguo: "ok" | ¿Hace tool call innecesaria? ¿Responde razonable? |
| D | Cierre: "Gracias, eso era todo" | ¿Intenta seguir preguntando? ¿Hace resumen apropiado? |

### 3.3 Métricas a registrar por modelo

```
Modelo: deepseek-v4-flash
├── Escenario A
│   ├── TTFT (time-to-first-token): X.Xs
│   ├── Latencia total: X.Xs
│   ├── Tokens generados: N
│   ├── ¿Llamó registrar_lead?: ✅/❌
│   ├── ¿Datos correctos?: ✅/❌
│   ├── ¿Una sola pregunta?: ✅/❌
│   └── Tool call innecesaria: ✅/❌
├── Escenario B
│   ├── TTFT: X.Xs
│   ├── Latencia total: X.Xs
│   ├── ¿Actualizó lead?: ✅/❌
│   └── ¿Tono natural?: 1-5
├── Escenario C
│   ├── Latencia total: X.Xs
│   ├── ¿Tool call innecesaria?: ✅/❌
│   └── ¿Respuesta razonable?: ✅/❌
├── Escenario D
│   ├── Latencia total: X.Xs
│   ├── ¿Resumen adecuado?: 1-5
│   └── ¿Intenta seguir preguntando?: ✅/❌
├── Latencia acumulada 4 escenarios: XX.Xs
├── Tool calls innecesarias total: N
└── Puntaje de calidad general: X/10
```

### 3.4 Ponderación para decisión final

| Criterio | Peso | Por qué |
|----------|------|---------|
| TTFT promedio | 25% | Determina la percepción de fluidez |
| Latencia total acumulada | 20% | Tiempo real de espera del lead |
| Tool calling correcto (sin innecesarias) | 25% | Cada tool call innecesaria agrega ~3-5s |
| Español rioplatense natural | 15% | Diferenciador clave del producto |
| Seguimiento de instrucciones | 15% | "Una pregunta por vez", no apurar |

---

## 4. Criterios de decisión

El modelo ideal para este caso de uso debe:

1. **TTFT < 2s** (para que el streaming se sienta instantáneo)
2. **Seguir instrucciones > 90%** ("una pregunta por vez", tool calls precisos)
3. **Tool calling confiable** (que llame a `registrar_lead` solo cuando corresponde)
4. **Español rioplatense natural** (no neutro genérico, que use "vos", "dale", "bárbaro")

### 4.1 Qué hacer si ningún modelo cumple todos los criterios

Si ningún modelo en el gateway logra TTFT < 2s + tool calling confiable + español natural,
la decisión será:

1. **Priorizar tool calling** por sobre latencia (un modelo lento pero correcto es mejor
   que uno rápido que borra datos o llama herramientas sin sentido).
2. **Evaluar si el problema de latencia está en el gateway mismo** — si todos los modelos
   tienen TTFT > 3s, la causa es el proxy, no los modelos.
3. **Mantener `deepseek-v4-flash`** como baseline y enfocarse en las optimizaciones del
   lado del agente (Plan 5: streaming, reducir tool calls innecesarias, fast-path para
   mensajes triviales).

---

## 5. Plan de ejecución

1. **Crear `scripts/benchmark_models.py`** — script que itera sobre los 7 modelos y los
   4 escenarios, midiendo las métricas definidas.
2. **Ejecutar el benchmark** (estimado: ~10-15 minutos para 7 modelos × 4 escenarios).
3. **Tabular resultados** y calcular el puntaje ponderado.
4. **Seleccionar el modelo ganador** y actualizar `src/config.py` + `.env`.
5. **Hacer una prueba de conversación completa** con el modelo ganador (simular la charla
   de Peter completa, 10 turnos).

---

## 6. Riesgos

- **El gateway puede tener latencia variable según carga** — hacer las pruebas en horario
  de baja demanda si es posible, o hacer 3 corridas por modelo y promediar.
- **Algunos modelos pueden no estar disponibles en el gateway** — verificar disponibilidad
  antes de correr el benchmark.
- **El comportamiento de tool calling puede variar entre runs** — para los escenarios más
  críticos (A y B), hacer 2-3 corridas y tomar el resultado más común.
