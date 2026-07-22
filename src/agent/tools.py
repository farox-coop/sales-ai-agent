"""Definiciones de tools en formato OpenAI/Anthropic Function Calling.

Cada tool describe qué hace, cuándo usarla y qué parámetros recibe.
El LLM decide autónomamente cuándo invocar cada una basándose en estas descripciones.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "registrar_lead",
            "description": (
                "Registra o actualiza los datos de identificación del lead en la base de datos. "
                "Llamala SOLO cuando el lead proporcione un dato NUEVO que no hayas registrado antes "
                "(nombre, email, empresa, cargo). No la llames por las dudas o 'para verificar': "
                "la tool te informa si los datos ya estaban registrados y no hubo cambios. "
                "Regla práctica: si en este turno el lead no dijo nada nuevo sobre su identidad, "
                "no llames a esta tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {
                        "type": "string",
                        "description": "Nombre completo del lead (ej. 'Juan Perez').",
                    },
                    "email": {
                        "type": "string",
                        "description": "Correo electrónico del lead (ej. 'juan@empresa.com').",
                    },
                    "empresa": {
                        "type": "string",
                        "description": "Nombre de la empresa donde trabaja.",
                    },
                    "cargo": {
                        "type": "string",
                        "description": "Cargo o rol del lead en la empresa (ej. 'CTO', 'Gerente de Innovación').",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "contador_preguntas",
            "description": (
                "Devuelve cuántas preguntas de diagnóstico se hicieron hasta ahora y cuántas "
                "quedan disponibles (el máximo es 12). Llamala para decidir si seguís explorando "
                "un dominio, si pasás a otro, o si vas cerrando. También para saber cuándo avisar "
                "al lead que quedan pocas preguntas."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_documentos",
            "description": (
                "Busca documentos relevantes en la base de conocimiento de Farox: propuestas "
                "comerciales, presupuestos, casos de éxito, documentos técnicos. Usala cuando "
                "el lead menciona una tecnología específica, un caso de uso, o pregunta si "
                "Farox tiene experiencia en algo. También si querés respaldar una recomendación "
                "con un caso real."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Texto de búsqueda, ej. 'machine learning en logística' o 'automatización de procesos'.",
                    },
                    "tipo": {
                        "type": "string",
                        "enum": ["propuesta", "cv", "presupuesto", "otro"],
                        "description": "Tipo de documento a buscar. Opcional, usar para filtrar.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_cv",
            "description": (
                "Busca perfiles profesionales (CVs) en la base de Farox que tengan experiencia "
                "en una tecnología o área específica. Usala cuando el lead pregunta '¿tienen a "
                "alguien que sepa X?' o '¿conocen gente con experiencia en Y?'. Responde con "
                "un resumen de los perfiles encontrados."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tecnologia": {
                        "type": "string",
                        "description": "Tecnología o skill a buscar, ej. 'Python', 'Computer Vision', 'RAG'.",
                    },
                },
                "required": ["tecnologia"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generar_resumen",
            "description": (
                "Genera el resumen estructurado del diagnóstico, lo guarda en la base de datos "
                "y cambia el estado del lead a 'completado'. Llamala ÚNICAMENTE cuando ya hayas "
                "terminado todas las preguntas (llegaste a 12 o el lead dio un panorama completo "
                "antes) y sea momento de cerrar la conversación. La tool devuelve el texto del "
                "resumen para que se lo muestres al lead junto con la despedida."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]
