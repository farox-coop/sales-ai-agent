---
type: concept
title: Stack Tecnológico
description: "Arquitectura de IA 100% open-source y self-hosted: hardware, inferencia, modelos, orquestación, interfaz y observabilidad."
tags: [tecnologia, stack, open-source, self-hosted, hardware, modelos, inferencia]
---

# Stack Tecnológico

## AI Open Stack — Arquitectura Libre

Construimos sobre estándares abiertos. Cada capa es auditable, reemplazable y de tu propiedad. Sin vendor lock-in. Sin cajas negras.

## Capas del Stack

### 1. Infraestructura Física (Hardware)
GPUs NVIDIA (H100/A100) o setups optimizados. Físico o cloud privado según tu caso.

- **Opción on-premise**: servidores con GPUs en tus instalaciones
- **Opción cloud privado**: infraestructura dedicada en datacenters de tu elección
- Sin dependencia de clouds públicos ni proveedores externos

### 2. Inferencia
Inferencia optimizada para máximo rendimiento en CPU y GPU propias.

- Motores de inferencia open-source (llama.cpp, vLLM, TGI)
- Optimización para hardware propio
- Sin llamadas a APIs externas que cobran por token

### 3. Modelos (Model Weights)
Administración eficiente de los pesos de los modelos. Actualización y control local.

- LLMs de clase mundial, abiertos y auditables. Sin cajas negras.
- Modelos open-source: Llama, Mistral, Qwen, DeepSeek y otros
- Control de versiones local de los modelos
- Actualización controlada sin dependencia externa

### 4. Orquestación
El "motor" de razonamiento: flujos de trabajo complejos y automatización sin código.

- Gestión de agentes y flujos de trabajo complejos
- Automatización sin código
- RAG (Retrieval-Augmented Generation) con bases de conocimiento propias

### 5. Interfaz (Client Layer)
IA integrada en el navegador, dispositivos móviles y entornos de desarrollo.

- Acceso amigable, chat y herramientas RAG para toda la organización
- Aplicaciones web y mobile
- Integración en entornos de desarrollo

### 6. Observabilidad (Capa Transversal)
Trazabilidad total de cada respuesta. Auditá, medí y optimizá el uso de IA con datos reales.

- **Diagnóstico y recomendación a medida**: análisis continuo de uso y rendimiento
- Monitoreo de todas las capas del stack
- Métricas de uso, costos y rendimiento
- Auditoría completa de interacciones

## Principios Tecnológicos

- **100% Open Source**: todo el stack usa tecnología de código abierto
- **Self-hosted**: todo corre en infraestructura propia del cliente
- **Auditable**: cada componente puede ser inspeccionado y verificado
- **Reemplazable**: ninguna capa genera vendor lock-in
- **Estándares abiertos**: APIs y protocolos estándar, sin formatos propietarios

Ver también: [[productos]], [[servicios-ia]]
