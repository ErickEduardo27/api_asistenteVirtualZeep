from pydantic_settings import BaseSettings
from typing import Optional
from urllib.parse import quote_plus


class Settings(BaseSettings):
    # Database
    postgres_user: str = "postgres"
    postgres_password: str = "edu_erickxto"
    postgres_db: str = "asistente_virtualZeep"
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432 

    @property
    def database_url(self) -> str:
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}"
            f"/{self.postgres_db}"
        )

    # JWT
    secret_key: str = "your-secret-key-change-this-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Google Gemini / LLM
    gemini_api_key: str = "AIzaSyBhY6UnT3PvMKvlQgW5hM6N2HxVXULc3cw"
    llm_model: str = "gemini-2.5-flash-lite"  # o "gemini-1.5-flash" para más velocidad
    embedding_model: str = "models/text-embedding-004"  # Modelo de embedding de Gemini

    # Rate Limiting
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000

    # Object Storage (MinIO)
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket_name: str = "documents"
    minio_use_ssl: bool = False

    # Application
    debug: bool = True
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
