from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings

# Crear engine asíncrono
engine = create_async_engine(
    settings.database_url,
    echo=True,
    future=True,
    connect_args={
        "ssl": None  # 👈 DESACTIVA SSL para Postgres local
    }
)

# Crear session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()


# Dependency para obtener sesión de DB
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

