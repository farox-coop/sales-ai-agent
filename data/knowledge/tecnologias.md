---
type: concept
title: Stack Tecnológico
description: "Arquitectura de IA 100% open-source y self-hosted en 7 capas más observabilidad transversal: hardware, inferencia, gestión, modelos, aplicativos, orquestación e interfaz."
tags: [tecnologia, stack, open-source, self-hosted, hardware, modelos, inferencia]
---

# Stack Tecnológico

## AI Open Stack — Arquitectura Libre

Construimos sobre estándares abiertos. Cada capa es auditable, reemplazable y de tu propiedad. Sin vendor lock-in. Sin cajas negras.

El stack se organiza en siete capas, de la infraestructura física hasta la interfaz de usuario, con una capa transversal de observabilidad.

## Capas del Stack

### 1. Hardware
Diagnóstico y recomendación a medida. GPUs NVIDIA (H100/A100) o setups optimizados. Físico o cloud privado según tu caso.

### 2. Motor de Inferencia
Ejecución eficiente de modelos sobre CPU y/o GPU. `llama.cpp`, optimizado para máximo rendimiento en hardware propio.

### 3. Gestión de Modelos
Administración eficiente de los pesos de los modelos, con actualización y control local. `Ollama`.

### 4. Modelos
El "motor" de razonamiento: LLMs de clase mundial, abiertos y auditables. Sin cajas negras. Modelos open-source como Llama 3.1, DeepSeek, Mistral, Phi-3, Qwen y Gemma, entre otros evaluables.

### 5. Aplicativos
IA integrada en el navegador, dispositivos móviles y entornos de desarrollo. Page Assist, M.A.I.D (mobile) y OpenCode.

### 6. Orquestación
Gestión de agentes y flujos de trabajo complejos. Automatización sin código. `Langflow` y `MCP`.

### 7. Interfaz
Acceso amigable, chat y herramientas RAG para toda la organización. `OpenWebUI`.

### Observabilidad (capa transversal)
Trazabilidad total de cada respuesta. Auditá, medí y optimizá el uso de IA con datos reales. `LangFuse`.

## Despliegue

Todo el stack corre en infraestructura propia de la organización (on-premise o cloud privado). Como alternativa, puede montarse una solución integrada para operar IA privada **dentro de la organización**, cerca de la operación, cuando los datos no deben salir del perímetro de confianza.

## Principios Tecnológicos

- **100% Open Source**: todo el stack usa tecnología de código abierto.
- **Self-hosted**: todo corre en infraestructura propia del cliente.
- **Auditable**: cada componente puede ser inspeccionado y verificado.
- **Reemplazable**: ninguna capa genera vendor lock-in.
- **Estándares abiertos**: APIs y protocolos estándar, sin formatos propietarios.

Ver también: [[inferencia]], [[genbase]], [[productos]], [[servicios-ia]], [[automatizacion-de-procesos]]
