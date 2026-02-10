"""
Script para inicializar la base de datos.
Ejecutar después de configurar PostgreSQL con pgvector.
"""
import asyncio
from sqlalchemy import text
from app.database import engine
from app.config import settings


async def init_db():
    """Inicializa la base de datos y crea la extensión pgvector."""
    async with engine.begin() as conn:
        # Crear extensión pgvector si no existe
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        print("✓ Extensión pgvector creada/verificada")
    
    print("✓ Base de datos inicializada")
    print(f"✓ Conectado a: {settings.database_url}")


if __name__ == "__main__":
    asyncio.run(init_db())

