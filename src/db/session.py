from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from src.config import settings

engine = create_async_engine(
    settings.sqlalchemy_async_url,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
)
async_session = async_sessionmaker(engine, expire_on_commit=False)
