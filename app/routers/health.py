from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/")
async def health_check():
    """Endpoint de health check básico."""
    return {
        "status": "healthy",
        "service": "asistente-virtual-api"
    }


@router.get("/db")
async def health_check_db(db: AsyncSession = Depends(get_db)):
    """Verifica la conexión a la base de datos."""
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        return {
            "status": "healthy",
            "database": "connected"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }

