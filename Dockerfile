FROM python:3.12-slim
WORKDIR /app

# Instalar dependencias (lista plana, sin compilar el package)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    chainlit>=2.0.0 \
    langgraph>=0.2.0 \
    langchain-core>=0.3.0 \
    langchain-openai>=0.2.0 \
    pydantic-settings>=2.0.0 \
    python-dotenv>=1.0.0 \
    httpx>=0.27.0 \
    beautifulsoup4>=4.12.0 \
    lxml>=5.0.0 \
    "sqlalchemy[asyncio]>=2.0.0" \
    asyncpg>=0.30.0 \
    psycopg2-binary>=2.9.0 \
    "alembic>=1.13.0" \
    "pyyaml>=6.0"

COPY src/ ./src/
COPY data/ ./data/

ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["chainlit", "run", "src/main.py", "--host", "0.0.0.0", "--port", "8000"]
