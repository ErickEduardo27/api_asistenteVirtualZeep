from pydantic_settings import BaseSettings
from typing import Optional
from urllib.parse import quote_plus


class Settings(BaseSettings):
    # Database
    postgres_user: str = "postgres"
    postgres_password: str = "edu_erickxto"
    postgres_db: str = "asistente_virtualZeep"
    postgres_host: str = "localhost"
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

    # OpenAI / LLM
    openai_api_key: Optional[str] = None
    llm_model: str = "gpt-4-turbo-preview"
    embedding_model: str = "text-embedding-3-small"

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
