from minio import Minio
from minio.error import S3Error
import structlog
from app.config import settings
from typing import Optional
import os

logger = structlog.get_logger()


class StorageService:
    """Servicio para almacenamiento de objetos (MinIO/S3)."""
    
    def __init__(self):
        self.client = None
        if all([
            settings.minio_endpoint,
            settings.minio_access_key,
            settings.minio_secret_key
        ]):
            try:
                self.client = Minio(
                    settings.minio_endpoint,
                    access_key=settings.minio_access_key,
                    secret_key=settings.minio_secret_key,
                    secure=settings.minio_use_ssl
                )
                self._ensure_bucket_exists()
            except Exception as e:
                logger.warning("MinIO not available, using local storage", error=str(e))
    
    def _ensure_bucket_exists(self):
        """Asegura que el bucket existe."""
        if not self.client:
            return
        try:
            if not self.client.bucket_exists(settings.minio_bucket_name):
                self.client.make_bucket(settings.minio_bucket_name)
                logger.info("Created bucket", bucket=settings.minio_bucket_name)
        except S3Error as e:
            logger.error("Error ensuring bucket exists", error=str(e))
    
    async def upload_file(
        self,
        file_path: str,
        object_name: str,
        content_type: Optional[str] = None
    ) -> str:
        """
        Sube un archivo al almacenamiento.
        
        Args:
            file_path: Ruta local del archivo
            object_name: Nombre del objeto en storage
            content_type: Tipo de contenido
            
        Returns:
            Ruta del archivo en storage
        """
        if self.client:
            try:
                self.client.fput_object(
                    settings.minio_bucket_name,
                    object_name,
                    file_path,
                    content_type=content_type
                )
                logger.info("File uploaded to MinIO", object_name=object_name)
                return f"{settings.minio_bucket_name}/{object_name}"
            except S3Error as e:
                logger.error("Error uploading to MinIO", error=str(e))
                raise
        
        # Fallback a almacenamiento local
        storage_dir = "storage/documents"
        os.makedirs(storage_dir, exist_ok=True)
        dest_path = os.path.join(storage_dir, object_name)
        
        import shutil
        shutil.copy2(file_path, dest_path)
        logger.info("File saved locally", path=dest_path)
        return dest_path
    
    async def download_file(self, object_name: str, dest_path: str) -> str:
        """
        Descarga un archivo del almacenamiento.
        
        Args:
            object_name: Nombre del objeto en storage
            dest_path: Ruta de destino local
            
        Returns:
            Ruta del archivo descargado
        """
        if self.client:
            try:
                self.client.fget_object(
                    settings.minio_bucket_name,
                    object_name,
                    dest_path
                )
                return dest_path
            except S3Error as e:
                logger.error("Error downloading from MinIO", error=str(e))
                raise
        
        # Fallback a almacenamiento local
        local_path = os.path.join("storage/documents", object_name)
        if os.path.exists(local_path):
            return local_path
        else:
            raise FileNotFoundError(f"File not found: {local_path}")

