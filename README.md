# IA Lead Magnet — Agente Conversacional

Agente conversacional con IA que reemplaza formularios estáticos por un diagnóstico adaptativo para leads interesados en adopción de IA. Guía al lead con preguntas dinámicas (~12), accede a conocimiento sobre [GenIA](https://genia.coop) y persiste el progreso de cada sesión.

Stack: **Chainlit** (UI) + **LangChain / LangGraph** (agente) + **PostgreSQL** (persistencia) + **Docker Compose**.

## Requisitos

- Docker y Docker Compose
- Un endpoint LLM OpenAI-compatible (API key + base URL)

## Ejecución local

```bash
# 1. Configurar variables de entorno
cp .env.example .env
# Editar .env con tu LLM_API_KEY y LLM_BASE_URL

# 2. Levantar los servicios con Docker Compose
make dev
```

Esto levanta dos contenedores: la app (Chainlit en `:8000`) y PostgreSQL. La app queda disponible en `http://localhost:8000`.

## Comandos útiles

| Comando | Descripción |
|---------|-------------|
| `make dev` | Build + levantar app y base de datos |
| `make down` | Bajar servicios y eliminar volúmenes |
| `make shell` | Abrir shell dentro del contenedor de la app |
| `make db-shell` | Conectarse a PostgreSQL |
| `make db-reset` | Recrear la base de datos desde cero |
| `make scrape-genia` | Scrapear contenido del sitio de GenIA |
| `make knowledge-reload` | Verificar carga de la base de conocimiento |

## Estructura

```
src/
├── agent/        # Lógica del agente (prompts, tools, loop)
├── chainlit/     # Hooks de interfaz conversacional
├── db/           # Modelos, migraciones y queries
├── knowledge/    # Base de conocimiento estática (GenIA)
└── config.py     # Configuración centralizada
```
