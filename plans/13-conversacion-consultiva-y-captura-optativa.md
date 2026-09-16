# Plan 13 — Conversación consultiva y captura optativa de leads

**Estado:** implementado (núcleo conversacional). Pendientes derivados al plan 14
**Fecha:** 2026-09-11
**Depende de:** planes 2, 3, 4, 5, 9 y 11 ya implementados
**Alcance:** rediseño conversacional y de persistencia

## Estado de implementación

### Completado

- Etapa 1: conversación consultiva sin captura forzada.
- Etapa 1.1: posicionamiento consultivo-comercial.
- Parte conversacional de la Etapa 2: captura optativa según intención comercial.
- Estado `contacto_solicitado` y migración `003`.
- Tool `solicitar_contacto` con persistencia básica.
- Canales institucionales condicionados a la intención del usuario.
- Tope blando de 12 turnos del usuario.
- Diagnóstico formal opt-in.
- IA soberana presentada como criterio, sin imponer on-premise, InferencIA o modelos locales.
- Tests existentes ejecutados correctamente dentro de Docker.
- Pruebas manuales iniciales de consultas institucionales, técnicas y comerciales.

### Pendiente (derivado al plan 14)

Los puntos que quedaban fuera del núcleo conversacional se trasladaron al
[plan 14](14-notificaciones-y-estados.md): notificación interna por SMTP, destinatario
configurable, persistencia de solicitudes y contexto, workflow de estados, tests específicos
y pruebas manuales post-SMTP.

Ninguno de esos puntos bloquea un despliegue a producción.

## 1. Objetivo

Reorientar el chatbot: la prioridad debe ser ayudar a la persona a entender su problema y las alternativas de solución, no obtener datos personales ni completar un diagnóstico comercial automáticamente.

La captura de datos, el registro del lead y el cierre formal pasan a ser acciones optativas, activadas por una señal de intención del usuario:

- pide hablar con GenIA;
- solicita una propuesta, presupuesto o diagnóstico;
- pide que le envíen información por email;
- acepta explícitamente avanzar;
- ofrece espontáneamente datos de contacto.

Una consulta exploratoria debe poder terminar sin pedir nombre, empresa ni email y sin presentar la interacción como un diagnóstico incompleto.

## 2. Hallazgos

### 2.1. Patrón de la conversación de referencia

La transcripción de `chat_example/transcripcion_chatbot.md` muestra un flujo consultivo:

1. El usuario plantea un problema concreto.
2. El chatbot responde directamente con varias alternativas posibles.
3. El usuario elige una línea y pide profundizar.
4. El chatbot explica conceptos y diferencias prácticas.
5. El usuario pregunta por tecnologías.
6. El chatbot presenta una arquitectura posible.
7. Ante una decisión concreta, compara RPA contra una arquitectura agéntica y recomienda una combinación.

Características a conservar:

- Responder primero; preguntar sólo cuando haga falta para mejorar la recomendación.
- Explicar alternativas y trade-offs, no empujar una única solución desde el inicio.
- Profundizar progresivamente según las preguntas del usuario.
- Usar lenguaje concreto y orientado al problema.
- Cerrar dejando abierta la posibilidad de explorar una solución a medida.

Observación importante: el chatbot de referencia contiene afirmaciones comerciales y técnicas que no deben copiarse automáticamente a GenIA. La KB de GenIA sigue siendo la fuente autorizada y las afirmaciones sobre tecnologías, despliegue, costos o capacidades deben respetar sus límites.

### 2.2. Sesgo actual del proyecto

El sistema actual está diseñado como un flujo de calificación:

- `GREETING` pide información sobre la persona y la empresa.
- El system prompt define como objetivo un diagnóstico de hasta 12 preguntas.
- La Fase 0 busca nombre y empresa al principio.
- El cierre presupone pedir email, generar resumen y completar el lead.
- `registrar_lead` y `contador_preguntas` forman parte del camino normal de casi toda conversación.
- `generar_resumen` cierra el lead y lo marca como `completado`.
- `on_chat_start` crea un registro `Lead` antes de que exista intención comercial.

El resultado puede sentirse como un formulario conversacional aunque el prompt diga que no lo es.

## 3. Decisiones cerradas

### Sesión y lead

Se mantiene el registro creado al iniciar la conversación, pero se lo trata como **lead anónimo/no calificado** hasta que exista intención comercial o datos de contacto relevantes. Esto permite conservar el cambio acotado y la persistencia actual sin considerar que toda sesión es automáticamente una oportunidad comercial.

### Contacto institucional

Cuando alguien pregunte cómo contactar a GenIA, el chatbot ofrecerá directamente:

- `hola@genia.coop`
- `https://genia.coop`

No debe pedir datos personales para responder esta consulta. Si la persona además quiere que GenIA la contacte, se activa el flujo de solicitud de seguimiento.

Los canales institucionales no se muestran por defecto. No deben aparecer como firma,
publicidad o cierre automático en respuestas técnicas o institucionales, aunque estén
incluidos en un artículo de la base de conocimiento. Sólo se ofrecen cuando la persona los
pide, expresa intención de contacto o seguimiento, solicita una propuesta o diagnóstico, o
cuando se confirma una solicitud comercial recién registrada. Si ya fueron mostrados y la
persona no los vuelve a pedir, no se repiten.

### Solicitud de resumen o propuesta

Inicialmente el sistema no enviará una propuesta automática al usuario. Cuando la persona pida un resumen, propuesta o seguimiento:

1. pedirá el email del usuario y los datos mínimos necesarios;
2. registrará la solicitud y el contexto de la conversación;
3. enviará un aviso a un email interno de GenIA para que el equipo realice la acción correspondiente;
4. confirmará al usuario que la solicitud fue registrada, sin prometer un plazo hasta que GenIA lo defina.

El email interno, proveedor de envío y plantilla de notificación quedan como decisiones pendientes.

### Diagnóstico formal

Se conserva como un modo **opt-in**. Sólo se activa cuando la persona acepta avanzar con un diagnóstico, propuesta o evaluación formal.

El límite deja de ser una obligación rígida de doce preguntas. El agente debe hacer sólo las preguntas relevantes para el objetivo acordado y cerrar cuando tenga información suficiente o alcance el tope blando definido para la implementación.

### Datos para seguimiento

Para una solicitud general de contacto, el **email es obligatorio**. El chatbot puede solicitar también nombre y empresa para brindar un trato más personal y dar contexto al equipo, pero ambos son opcionales: si la persona no quiere compartirlos, la solicitud igualmente puede registrarse con email.

Para una solicitud explícita de propuesta o diagnóstico formal, se solicitarán **nombre, empresa y email** como contexto mínimo esperado para iniciar una oportunidad comercial.

La conversación debe explicar por qué se solicita cada dato y no insistir si la persona no quiere compartir un dato opcional.

## 4. Nuevo modelo de conversación

### Modo A — Exploración y consulta

Es el modo predeterminado.

El agente:

- responde preguntas sobre GenIA usando la base de conocimiento;
- entiende el problema del usuario;
- propone alternativas plausibles;
- compara soluciones, limitaciones, dependencias y próximos pasos;
- hace preguntas de contexto sólo si son necesarias para responder mejor;
- no solicita datos personales por defecto;
- no llama `registrar_lead` sólo porque apareció un nombre o una empresa en una frase contextual, salvo que el usuario ofrezca esos datos como contacto o pida avanzar.

### Modo B — Exploración técnica guiada

Se activa cuando el usuario quiere diseñar una solución o pide evaluar opciones.

El agente puede hacer preguntas relevantes al problema, por ejemplo:

- qué sistema interviene;
- si existe API o sólo interfaz web;
- volumen de documentos o transacciones;
- variabilidad de formatos;
- nivel de revisión humana requerido;
- restricciones de datos e infraestructura.

Estas preguntas son sobre el problema, no sobre la identidad del usuario. Habrá un **tope de interacción** para evitar conversaciones eternas, pero alcanzar ese tope no implica cerrar comercialmente ni pedir datos obligatoriamente. Al acercarse al límite, el agente debe resumir lo entendido y ofrecer opciones: continuar con una aclaración puntual, recibir los datos de contacto de GenIA o solicitar un seguimiento.

El tope debe ser una protección conversacional, no un contador visible ni un objetivo que el agente deba completar.

El tope inicial será de **12 turnos del usuario** para la exploración. Al acercarse o alcanzarlo, el agente debe resumir lo entendido y ofrecer continuar mediante una solicitud de contacto/seguimiento o dejar los canales institucionales, sin exigir datos ni marcar automáticamente la conversación como completada.

### Modo C — Avance comercial voluntario

Se activa cuando existe intención explícita de contacto o seguimiento.

El agente debe:

1. reconocer la intención;
2. explicar qué puede ofrecer GenIA como siguiente paso;
3. pedir sólo los datos necesarios para esa acción;
4. registrar los datos nuevos;
5. ofrecer los canales institucionales disponibles;
6. confirmar qué ocurrirá con los datos, sin prometer un plazo no documentado.

Ejemplos:

- “Quiero hablar con alguien” → pedir un canal de contacto, empezando por email si es el canal definido.
- “¿Me pueden mandar una propuesta?” → pedir email y, si hace falta, nombre/organización para identificar la solicitud.
- “Quiero un diagnóstico” → ofrecer el diagnóstico y pedir los datos mínimos para coordinarlo.
- “Sólo estoy investigando” → continuar ayudando sin pedir datos.

### Modo D — Cierre natural

Si el usuario no quiere avanzar, el agente responde la consulta y finaliza con una invitación no invasiva. No genera resumen comercial, no marca el lead como completado y no insiste con datos.

## 5. Separar intención de datos

El prompt y el agente deben distinguir explícitamente:

- **Contexto de negocio:** información sobre el problema, proceso, sistemas, volumen, restricciones y objetivos.
- **Identidad:** nombre, email, empresa y cargo.
- **Intención comercial:** interés en contacto, propuesta, diagnóstico o seguimiento.
- **Preferencia de contacto:** email u otro canal aceptado por GenIA.

Conocer contexto de negocio no implica que haya que crear o completar un lead.

## 6. Cambios previstos en el system prompt

Reemplazar el objetivo de “hacer un diagnóstico de máximo 12 preguntas” por una instrucción de asistencia consultiva.

El nuevo prompt debería incluir:

- prioridad: resolver la consulta del usuario antes de intentar convertirlo;
- modo predeterminado sin captura de datos;
- preguntas sólo cuando aportan valor a la respuesta;
- prohibición de pedir nombre, empresa o email como saludo estándar;
- activación de captura sólo por intención explícita o entrega espontánea relevante;
- no usar `contador_preguntas` en consultas normales;
- no usar `generar_resumen` como cierre automático;
- no inventar capacidades, integraciones, tecnologías, costos o casos de éxito;
- presentar como hipótesis o alternativa las soluciones que requieran diagnóstico técnico;
- mantener el tono rioplatense, cálido, conciso y no invasivo.

Se recomienda agregar ejemplos few-shot de:

- consulta exploratoria respondida sin pedir datos;
- problema técnico con preguntas de contexto;
- solicitud explícita de propuesta con captura de email;
- rechazo a compartir datos respetado sin insistencia;
- dato de contacto ofrecido espontáneamente y registrado una sola vez.

## 7. Tools y ciclo de vida

### `listar_articulos` y `leer_articulo`

Se mantienen. Deben usarse para responder sobre GenIA, sus soluciones, tecnologías, sectores y metodología.

### `registrar_lead`

Se mantiene, pero deja de ser una acción esperada de la conversación. El prompt debe exigir una señal clara:

- solicitud de contacto, propuesta, diagnóstico o seguimiento;
- o dato de contacto ofrecido espontáneamente.

La tool no debe registrar datos sólo porque el agente los preguntó sin necesidad.

### `contador_preguntas`

Deja de ser una tool central del diagnóstico comercial, pero puede reutilizarse o reemplazarse para proteger el límite conversacional. Hay dos opciones:

1. conservarla para un futuro diagnóstico formal, pero no incluirla en el agente consultivo general;
2. reemplazarla por un contador de preguntas de contexto si realmente se necesita limitar preguntas en el modo técnico.

La recomendación inicial es separar el contador técnico del concepto de diagnóstico: usar un límite blando para la exploración y reservar el diagnóstico estructurado para cuando la persona acepte avanzar.

### `generar_resumen`

No debe cerrar automáticamente una consulta. Se recomienda separar dos acciones:

- resumen útil para el usuario dentro de la respuesta, sin persistir ni completar el lead;
- resumen comercial persistido sólo cuando el usuario solicita avanzar o acepta un diagnóstico.

La tool actual mezcla generación de resumen, persistencia y cambio de estado. Esa responsabilidad debe dividirse o protegerse con una condición explícita de intención comercial.

### `buscar_cv`

Se mantiene como respuesta honesta si alguien pregunta por perfiles o experiencia. No debe disparar captura de datos por sí misma.

## 8. Persistencia y estados

### Problema actual

`on_chat_start` crea un `Lead` inmediatamente. Eso confunde sesión conversacional con lead comercial y dificulta medir conversión real.

### Diseño recomendado

Mantener un identificador técnico de sesión y separar su existencia de la calificación comercial.

Alternativas:

1. **Cambio mínimo:** seguir creando `Lead`, pero agregar un estado o indicador que distinga sesión anónima de lead identificado.
2. **Modelo más limpio:** crear una entidad de sesión/interacción anónima y crear `Lead` sólo al aparecer intención o datos de contacto.

La implementación debería elegir la opción 1 si se prioriza un cambio acotado, o la opción 2 si se quiere corregir el modelo de dominio de forma definitiva.

Estados sugeridos si se mantiene `Lead` desde el inicio:

- `activo` o sesión anónima: conversación abierta sin intención comercial confirmada;
- `interesado`: el usuario expresó interés en avanzar, aunque falten datos;
- `contacto_solicitado`: pidió contacto, propuesta o seguimiento; este estado se agrega al modelo actual y representa que existe una solicitud comercial registrada;
- `completado`: se obtuvo el mínimo necesario y se generó una entrega comercial;
- `abandonado`: sesión interrumpida, sin asumir que es un lead calificado.

No se recomienda reutilizar `completado` para cualquier conversación que simplemente terminó.

### Datos de contexto

El contexto técnico y las necesidades detectadas pueden persistirse en `extra_data` sólo si existe valor operativo, pero deben distinguirse de los datos personales y no convertir automáticamente la sesión en lead.

## 9. Notificación interna de solicitudes

Cuando se registre una solicitud de contacto, propuesta, resumen o seguimiento, debe generarse una notificación interna con, como mínimo:

- fecha y hora;
- email del usuario y demás datos proporcionados;
- tipo de solicitud;
- resumen de la necesidad;
- transcripción o referencia a la conversación;
- estado inicial de seguimiento.

La notificación debe ser best-effort y observable: si falla el envío, la solicitud debe conservarse en la base de datos para que no se pierda.

La implementación deberá definir un adaptador de email y variables de entorno, sin hardcodear credenciales ni destinatarios sensibles.

El destinatario interno y el proveedor de envío quedan configurables mediante variables de entorno. No se fija una dirección real en el código ni en este plan.

La primera implementación usará **SMTP configurable** por variables de entorno. No se adopta todavía un proveedor transaccional específico.

## 10. Contacto institucional

La base de conocimiento contiene el sitio y el email institucional de GenIA. El agente debe poder ofrecer esos canales cuando el usuario pregunta cómo contactar, sin pedir primero los datos del usuario.

Si GenIA quiere que el chatbot ofrezca un canal específico (email, formulario, WhatsApp, agenda), debe definirse una fuente única y actualizable para esos datos. No se deben inventar teléfonos, links de agenda ni plazos de respuesta.

## 11. Criterios de aceptación conversacionales

### Consulta exploratoria

- El primer turno responde la pregunta o pide una aclaración sobre el problema.
- No solicita nombre, empresa ni email.
- No llama `registrar_lead`, `contador_preguntas` ni `generar_resumen`.

### Consulta técnica

- Explica al menos una alternativa viable y sus trade-offs.
- Hace sólo preguntas relevantes para resolver la situación.
- Puede sugerir RPA, agentes, RAG, desarrollo custom, Genway o InferencIA sólo cuando la KB lo respalda y con el nivel de certeza adecuado.

### Solicitud de contacto

- Reconoce explícitamente que el usuario quiere avanzar.
- Pide el mínimo de datos necesarios.
- Llama `registrar_lead` sólo con datos nuevos.
- Ofrece el canal institucional correspondiente.
- No pide doce preguntas antes de tomar el contacto.

### Rechazo a compartir datos

- Respeta el rechazo en el mismo turno.
- Continúa ayudando o ofrece los canales públicos de GenIA.
- No vuelve a pedir datos en los turnos siguientes salvo que el usuario cambie de intención.

### Conversación larga

- No fuerza un resumen comercial por cantidad de mensajes.
- No anuncia que “faltan preguntas”.
- Puede cerrar con un resumen útil de lo conversado sin cambiar el estado comercial.

## 12. Pruebas manuales requeridas

Antes de implementar definitivamente, probar en Docker al menos estos escenarios:

1. “¿Qué hace GenIA?”
2. “Sólo estoy investigando, no quiero que me contacten.”
3. “Tenemos facturas en PDF y un sistema web sin API. ¿Cómo se puede automatizar?”
4. “¿Me pueden preparar una propuesta?”
5. “Quiero hablar con alguien de GenIA.”
6. “Mi nombre es Ana y mi email es ana@empresa.com.”
7. Usuario que cambia de opinión: primero rechaza contacto y luego lo solicita.
8. Usuario que pide una respuesta técnica sin revelar nombre, empresa ni email.
9. Usuario que pregunta por una capacidad no presente en la KB.
10. Usuario que pregunta por tecnologías específicas y por el alcance de un desarrollo a medida.

Para cada escenario registrar:

- respuesta visible;
- tools llamadas;
- datos escritos en DB;
- estado final del lead/sesión;
- si pidió información personal sin que correspondiera;
- si presentó una recomendación con certeza adecuada.

## 13. Etapas de implementación

### Etapa 1 — Conversación consultiva sin captura forzada

Objetivo: que el chatbot responda y explore necesidades sin pedir datos por defecto.

- Reescribir el system prompt.
- Eliminar la Fase 0 obligatoria.
- Convertir `contador_preguntas` en un mecanismo interno de límite, no de calificación.
- Definir el tope blando de 12 turnos del usuario.
- Mantener las tools de conocimiento activas.
- Probar que una consulta exploratoria no llama `registrar_lead` ni `generar_resumen`.

### Etapa 1.1 — Posicionamiento consultivo-comercial

Objetivo: que el chatbot no se limite a explicar alternativas técnicas, sino que represente
a GenIA como un socio capaz de diseñar, implementar y acompañar una solución.

Ante una necesidad concreta, la respuesta debe seguir este orden:

1. Reconocer el problema y demostrar que entendió el objetivo.
2. Comunicar que GenIA puede abordarlo y diseñar una solución a medida.
3. Describir brevemente cómo podría implementarse, sin cerrar prematuramente la arquitectura.
4. Explicar alternativas, combinaciones y trade-offs.
5. Indicar qué aspectos habría que validar antes de definir la solución final.
6. Hacer sólo las preguntas necesarias para avanzar.
7. Ofrecer continuar con GenIA, sin exigir datos personales.

En la **primera respuesta** a una necesidad concreta, no cerrar con preguntas técnicas
sobre volumen, formatos, APIs, infraestructura o flujo operativo. El cierre debe ser una
invitación abierta y comercial a conversar para entender el desafío y diseñar una solución
a medida. El relevamiento técnico empieza sólo si la persona acepta profundizar, pide una
recomendación más precisa o aporta voluntariamente más contexto.

El agente debe hablar desde la capacidad de GenIA —“podemos diseñar”, “podemos implementar”,
“podemos evaluar”, “acompañamos la puesta en marcha”— y no desde una posición de consultor
neutral que entrega instrucciones para que el usuario resuelva el problema por su cuenta.

Este posicionamiento no autoriza a prometer una tecnología, plazo, costo, integración,
resultado o disponibilidad concreta sin validación. La confianza comercial debe surgir de
la capacidad de hacerse cargo del problema, no de afirmar una solución cerrada antes de
conocer el contexto.

La IA soberana debe comunicarse como el criterio rector de GenIA —control sobre datos,
arquitectura, políticas y evolución tecnológica—, no como sinónimo obligatorio de una
implementación íntegramente on-premise. El chatbot puede proponer infraestructura propia,
cloud privado, servicios externos autorizados o combinaciones según sensibilidad de datos,
seguridad, disponibilidad, costos, normativa y capacidades internas.

InferencIA debe presentarse como una arquitectura abierta de referencia que puede formar
parte de la solución cuando conviene operar componentes bajo control de la organización,
no como requisito de todo proyecto. Tampoco deben convertirse automáticamente en garantías
las frases “100% local”, “sin proveedores externos” o “costo cero por consulta”.

Las frases de referencia son sólo una guía de intención y tono. No deben incorporarse como
plantillas literales al prompt ni copiarse en las respuestas. El agente debe redactar cada
cierre con lenguaje propio, adaptado al problema y al momento de la conversación.

### Etapa 2 — Intención comercial y captura optativa

Objetivo: activar el flujo comercial sólo cuando el usuario pide avanzar.

- Definir detección de intención de contacto, propuesta, diagnóstico o seguimiento.
- Ajustar `registrar_lead` para capturar sólo datos nuevos y relevantes.
- Aplicar email obligatorio para contacto general.
- Aplicar nombre + empresa + email para propuesta o diagnóstico formal.
- Mantener nombre y empresa opcionales en el contacto general.
- Ofrecer siempre `hola@genia.coop` y `https://genia.coop` cuando corresponda.

### Etapa 3 — Diagnóstico formal opt-in

Objetivo: conservar el diagnóstico como una experiencia elegida por el usuario, no como el comportamiento por defecto.

- Rediseñar el diagnóstico para hacer sólo preguntas relevantes.
- Mantener el tope de protección sin convertirlo en una lista obligatoria.
- Separar resumen conversacional de resumen comercial persistido.
- Usar `generar_resumen` sólo después de aceptación explícita o intención equivalente.

### Etapa 4 — Solicitud y aviso interno

Objetivo: registrar una solicitud de seguimiento y avisar al equipo de GenIA.

- Persistir tipo de solicitud y contexto relevante.
- Implementar adaptador de email configurable.
- Enviar aviso interno best-effort.
- Conservar la solicitud si el envío falla.
- Confirmar al usuario el registro sin prometer plazos.

### Etapa 5 — Estados, métricas y validación

Objetivo: distinguir conversaciones anónimas de oportunidades comerciales y comprobar el comportamiento real.

- Mantener el lead anónimo/no calificado al iniciar.
- Agregar el estado `contacto_solicitado` al modelo actual.
- Definir transición a `interesado`, `contacto_solicitado` y `completado`.
- Revisar `on_chat_start` y `on_stop`.
- Agregar tests de regresión conversacional y de persistencia.
- Probar end-to-end dentro de Docker y revisar logs de tools.

## 14. Decisiones pendientes antes de implementar

- ¿Qué proveedor/adaptador de email se usará para las notificaciones?
- ¿Qué dirección interna debe recibir las notificaciones SMTP?

El seguimiento se modelará inicialmente con **la fecha del aviso**. No habrá asignación individual ni workflow de estados adicional en la primera implementación.

Cuando el usuario consulte por tecnologías o soluciones generales no descritas explícitamente en la KB, el chatbot podrá explicarlas con cautela y presentarlas como alternativas que GenIA puede evaluar y aplicar según el caso. Debe mantener una postura segura y orientada a resolver, sin afirmar detalles técnicos, resultados, integraciones o disponibilidad que no hayan sido validados.

## 15. Riesgos y límites

- Un modelo puede volver a pedir datos aunque el prompt lo prohíba; conviene agregar validaciones observables en código y tests de regresión.
- Si se elimina completamente el límite de preguntas, una conversación técnica puede volverse larga; debe controlarse por utilidad y posiblemente por un límite blando.
- La conversación de referencia recomienda “arquitecturas agénticas”, cloud y tecnologías concretas. GenIA no debe adoptar esas afirmaciones sin verificar que están en su fuente de verdad.
- “Simular interacción humana” no implica que todos los sistemas puedan automatizarse sin API, selectores estables, permisos, auditoría y revisión humana.
- Los datos de contacto requieren una política explícita de privacidad, retención y uso para seguimiento.
