import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.schemas.document import DocumentResponse, DocumentIngestResponse
from app.models.document import Document, DocumentStatus
from app.services.storage import StorageService
from app.services.document_processor import DocumentProcessor
from app.services.auth import get_current_active_user
from app.models.user import User

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Sube un documento para procesamiento posterior.
    """
    # Validar tipo de archivo
    allowed_types = ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type {file.content_type} not allowed. Allowed types: PDF, DOCX, TXT"
        )
    
    # Guardar archivo temporalmente
    file_extension = os.path.splitext(file.filename)[1]
    temp_filename = f"{uuid.uuid4()}{file_extension}"
    temp_path = f"temp/{temp_filename}"
    
    os.makedirs("temp", exist_ok=True)
    
    try:
        # Guardar archivo temporal
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        file_size = len(content)
        
        # Subir a storage
        storage_service = StorageService()
        object_name = f"{current_user.id}/{uuid.uuid4()}{file_extension}"
        storage_path = await storage_service.upload_file(
            temp_path,
            object_name,
            content_type=file.content_type
        )
        
        # Crear registro en BD
        document = Document(
            user_id=current_user.id,
            filename=file.filename,
            file_path=storage_path,
            file_type=file_extension[1:].lower(),  # Sin el punto
            file_size=file_size,
            status=DocumentStatus.UPLOADED
        )
        
        db.add(document)
        await db.commit()
        await db.refresh(document)
        
        # Limpiar archivo temporal
        os.remove(temp_path)
        
        return document
        
    except Exception as e:
        # Limpiar en caso de error
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error uploading document: {str(e)}"
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

