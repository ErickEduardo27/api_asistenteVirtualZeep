from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class PresignedUrlRequest(BaseModel):
    filename: str
    file_type: str
    file_size: int


class PresignedUrlResponse(BaseModel):
    presigned_url: str
    object_name: str
    expires_in: int  # segundos


class DocumentMetadata(BaseModel):
    filename: str
    file_type: str
    file_size: int
    object_name: str  # Nombre del objeto en MinIO


class DocumentResponse(BaseModel):
    id: int
    filename: str
    file_type: str
    file_size: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentIngestResponse(BaseModel):
    document_id: int
    chunks_created: int
    embeddings_created: int
    status: str

