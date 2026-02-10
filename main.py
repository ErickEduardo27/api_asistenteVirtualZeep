import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.database import engine, Base
from app.middleware.rate_limit import setup_rate_limiting
from app.middleware.logging import LoggingMiddleware
from app.routers import auth, chat, documents, health

# Configurar logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events: startup y shutdown."""
    # Startup
    logger = structlog.get_logger()
    logger.info("Starting application")
    
    # Crear tablas si no existen (en producción usar Alembic)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created/verified")
    except Exception as e:
        logger.error("Error creating database tables", error=str(e))
    
    yield
    
    # Shutdown
    logger.info("Shutting down application")
    await engine.dispose()


# Crear aplicación FastAPI
app = FastAPI(
    title="Asistente Virtual API",
    description="API para asistente virtual con RAG y streaming",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especificar dominios
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware de logging
app.add_middleware(LoggingMiddleware)

# Rate limiting
app = setup_rate_limiting(app)

# Incluir routers
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(documents.router, prefix=settings.api_prefix)
app.include_router(health.router)


@app.get("/")
async def root():
    """Endpoint raíz."""
    return {
        "status": "Asistente Virtual API",
        "version": "1.0.0",
        "docs": "/docs"
    }
