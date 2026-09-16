# Plan 14 — Notificaciones internas, persistencia de solicitudes y estados

**Estado:** propuesta de implementación
**Fecha:** 2026-09-16
**Depende de:** plan 13 (núcleo conversacional ya implementado)
**Alcance:** cierre operativo del flujo comercial: aviso interno, persistencia completa, workflow de estados y cobertura de tests

## 1. Objetivo

Completar lo que el plan 13 dejó fuera del núcleo conversacional. El chat consultivo ya
funciona y `solicitar_contacto` persiste datos básicos; falta el aviso interno, la
persistencia completa del contexto de solicitud, la revisión del workflow de estados y la
cobertura específica de tests.

No bloquea un despliegue a producción: el equipo puede trackear manualmente las solicitudes
que queden en `extra_data["ultima_solicitud"]` hasta que este plan se ejecute.

## 2. Pendientes heredados del plan 13

1. Implementar notificación interna por SMTP.
2. Definir el destinatario interno mediante configuración.
3. Completar la persistencia de solicitudes y contexto de conversación.
4. Revisar el workflow completo de estados (`activo`, `interesado`, `contacto_solicitado`, `completado` y `abandonado`).
5. Agregar tests específicos de la nueva lógica conversacional y comercial.
6. Ejecutar una ronda adicional de pruebas manuales después de implementar SMTP.

## 3. Notificación interna por SMTP

Al registrar una solicitud de contacto, propuesta, resumen o seguimiento, generar un aviso
interno con, como mínimo:

- fecha y hora;
- email del usuario y demás datos proporcionados;
- tipo de solicitud;
- resumen de la necesidad;
- transcripción o referencia a la conversación;
- estado inicial de seguimiento.

Requisitos:

- Adaptador de email configurable por variables de entorno, sin hardcodear credenciales ni destinatarios.
- Best-effort y observable: si falla el envío, la solicitud se conserva en la base de datos.
- Primera implementación con **SMTP configurable** por variables de entorno. Sin proveedor transaccional específico.
- La dirección interna destinataria queda configurable por variable de entorno.

## 4. Persistencia de solicitudes y contexto

Hoy `solicitar_contacto` sólo escribe `extra_data["ultima_solicitud"] = {tipo, registrada_en}`.
Falta persistir de forma consultable:

- tipo de solicitud (contacto, propuesta, presupuesto, diagnostico, resumen);
- datos proporcionados (email, nombre, empresa);
- contexto técnico / necesidad detectada;
- referencia o transcripción de la conversación;
- estado inicial de seguimiento.

Se debe distinguir contexto de negocio de datos personales y no convertir automáticamente
la sesión en lead calificado.

## 5. Workflow de estados

El enum actual (`LeadStatus`) tiene `activo`, `contacto_solicitado`, `completado` y
`abandonado`. El plan 13 planteó además `interesado`, que **no fue agregado al modelo**.

- Definir si `interesado` se agrega o se descarta.
- Definir transiciones: `activo → interesado → contacto_solicitado → completado` y
  `→ abandonado`.
- Revisar `on_chat_start` y `on_stop` (hoy crean un `Lead` activo y lo cierran como
  `abandonado`).
- No reutilizar `completado` para una conversación que simplemente terminó.
- El seguimiento se modela inicialmente con la fecha del aviso; sin asignación individual.

## 6. Tests

Agregar tests de regresión conversacional y de persistencia, cubriendo:

- consulta exploratoria sin llamadas a `registrar_lead`, `contador_preguntas` ni `generar_resumen`;
- solicitud de contacto con email obligatorio y nombre/empresa opcionales;
- propuesta o diagnóstico formal con nombre + empresa + email;
- rechazo a compartir datos respetado sin insistencia;
- canales institucionales mostrados sólo cuando corresponde;
- transiciones de estado correctas.

## 7. Pruebas manuales

Tras implementar SMTP, ejecutar una ronda manual en Docker con los escenarios del plan 13
(sección 12), registrando respuesta visible, tools llamadas, datos en DB, estado final y
cumplimiento de los criterios de aceptación (sección 11).

## 8. Decisiones pendientes

- ¿Qué proveedor/adaptador de email se usará para las notificaciones?
- ¿Qué dirección interna debe recibir las notificaciones SMTP?
- ¿Se adopta el estado `interesado` o se elimina del modelo?
