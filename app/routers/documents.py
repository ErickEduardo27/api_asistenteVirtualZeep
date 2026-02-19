import os
import uuid
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.schemas.document import (
    DocumentResponse, 
    DocumentIngestResponse,
    PresignedUrlRequest,
    PresignedUrlResponse,
    DocumentMetadata
)
from app.models.document import Document, DocumentStatus
from app.services.storage import StorageService
from app.services.document_processor import DocumentProcessor
from app.services.auth import get_current_active_user
from app.models.user import User

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/presigned-url", response_model=PresignedUrlResponse)
async def get_presigned_url(
    request: PresignedUrlRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    Genera una URL firmada (presigned URL) para que el frontend suba el archivo directamente a MinIO.
    """
    # Validar tipo de archivo
    allowed_types = ["pdf", "docx", "txt"]
    file_type_lower = request.file_type.lower()
    if file_type_lower not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type {request.file_type} not allowed. Allowed types: PDF, DOCX, TXT"
        )
    
    # Generar nombre único para el objeto en MinIO
    file_extension = f".{file_type_lower}"
    object_name = f"{current_user.id}/{uuid.uuid4()}{file_extension}"
    
    # Generar presigned URL
    storage_service = StorageService()
    try:
        presigned_url = storage_service.generate_presigned_url(
            object_name=object_name,
            expires=timedelta(hours=1),
            method="PUT"
        )
        
        return PresignedUrlResponse(
            presigned_url=presigned_url,
            object_name=object_name,
            expires_in=3600  # 1 hora en segundos
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating presigned URL: {str(e)}"
        )


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document_metadata(
    metadata: DocumentMetadata,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Registra la metadata de un documento después de que el frontend lo haya subido a MinIO.
    El archivo ya debe estar en MinIO usando la presigned URL.
    """
    # Validar que el object_name pertenece al usuario actual
    if not metadata.object_name.startswith(f"{current_user.id}/"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid object name for current user"
        )
    
    # Validar tipo de archivo
    allowed_types = ["pdf", "docx", "txt"]
    file_type_lower = metadata.file_type.lower()
    if file_type_lower not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type {metadata.file_type} not allowed. Allowed types: PDF, DOCX, TXT"
        )
    
    try:
        # Crear registro en BD
        document = Document(
            user_id=current_user.id,
            filename=metadata.filename,
            file_path=metadata.object_name,  # El object_name es el path en MinIO
            file_type=file_type_lower,
            file_size=metadata.file_size,
            status=DocumentStatus.UPLOADED
        )
        
        db.add(document)
        await db.commit()
        await db.refresh(document)
        
        return document
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving document metadata: {str(e)}"
        )


@router.post("/{document_id}/ingest", response_model=DocumentIngestResponse)
async def ingest_document(
    document_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Procesa un documento: extrae texto, crea chunks y embeddings.
    """
    # Obtener documento
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == current_user.id
        )
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    if document.status == DocumentStatus.PROCESSING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document is already being processed"
        )
    try:
        # Descargar archivo del storage
        storage_service = StorageService()
        temp_path = f"temp/{uuid.uuid4()}"
        os.makedirs("temp", exist_ok=True)
        
        await storage_service.download_file(document.file_path, temp_path)
        
        # Procesar documento
        processor = DocumentProcessor()
        chunks_created, embeddings_created = await processor.process_document(
            db, document, temp_path
        )

        await db.commit()   # 🔥 ESTO FALTABA
        
        # Limpiar archivo temporal
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        return DocumentIngestResponse(
            document_id=document.id,
            chunks_created=chunks_created,
            embeddings_created=embeddings_created,
            status=document.status.value
        )
        
    except Exception as e:
        # Limpiar en caso de error
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing document: {str(e)}"
        )


@router.get("/", response_model=list[DocumentResponse])
async def list_documents(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Lista todos los documentos del usuario."""
    result = await db.execute(
        select(Document).where(Document.user_id == current_user.id)
    )
    documents = result.scalars().all()
    return documents

