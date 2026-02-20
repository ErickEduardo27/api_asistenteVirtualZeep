import structlog
import os
import shutil
from typing import Optional

logger = structlog.get_logger()


class StorageService:
    """Servicio para almacenamiento local de documentos."""
    
    def __init__(self):
        # Directorio base para almacenar documentos
        self.storage_dir = "storage/documents"
        os.makedirs(self.storage_dir, exist_ok=True)
        logger.info("Storage service initialized", storage_dir=self.storage_dir)
    
    async def upload_file(
        self,
        file_path: str,
        object_name: str,
        content_type: Optional[str] = None
    ) -> str:
        """
        Guarda un archivo en el almacenamiento local.
        
        Args:
            file_path: Ruta local del archivo fuente
            object_name: Nombre del objeto en storage (puede incluir subdirectorios)
            content_type: Tipo de contenido (no usado en almacenamiento local)
            
        Returns:
            Ruta relativa del archivo guardado
        """
        try:
            # Crear subdirectorios si es necesario (ej: user_id/)
            dest_path = os.path.join(self.storage_dir, object_name)
            dest_dir = os.path.dirname(dest_path)
            if dest_dir:
                os.makedirs(dest_dir, exist_ok=True)
            
            # Copiar archivo al almacenamiento
            shutil.copy2(file_path, dest_path)
            logger.info("File saved locally", path=dest_path, object_name=object_name)
            
            # Retornar la ruta relativa para guardar en BD
            return object_name
        except Exception as e:
            logger.error("Error saving file locally", error=str(e), object_name=object_name)
            raise
    
    async def download_file(self, object_name: str, dest_path: str) -> str:
        """
        Copia un archivo del almacenamiento local a una ruta temporal.
        
        Args:
            object_name: Nombre del objeto en storage (ruta relativa)
            dest_path: Ruta de destino local
            
        Returns:
            Ruta del archivo copiado
        """
        try:
            source_path = os.path.join(self.storage_dir, object_name)
            
            if not os.path.exists(source_path):
                raise FileNotFoundError(f"File not found: {source_path}")
            
            # Asegurar que el directorio de destino existe
            dest_dir = os.path.dirname(dest_path)
            if dest_dir:
                os.makedirs(dest_dir, exist_ok=True)
            
            # Copiar archivo
            shutil.copy2(source_path, dest_path)
            logger.info("File copied from storage", source=source_path, dest=dest_path)
            return dest_path
        except Exception as e:
            logger.error("Error copying file from storage", error=str(e), object_name=object_name)
            raise

