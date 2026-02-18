from typing import List
import os
from pathlib import Path
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk, DocumentStatus
from app.services.rag import RAGService

from sqlalchemy import delete, select
from app.models.embedding import Embedding

logger = structlog.get_logger()


class DocumentProcessor:
    """Servicio para procesar documentos: chunking y extracción de texto."""
    
    def __init__(self):
        self.rag_service = RAGService()
        self.chunk_size = 1000  # Tamaño de chunk en caracteres
        self.chunk_overlap = 200  # Overlap entre chunks
    
    async def process_document(
        self,
        db: AsyncSession,
        document: Document,
        file_path: str
    ) -> tuple[int, int]:
        """
        Procesa un documento: extrae texto, crea chunks y embeddings.
        
        Args:
            db: Sesión de base de datos
            document: Documento a procesar
            file_path: Ruta al archivo
            
        Returns:
            Tupla con (chunks_created, embeddings_created)
        """
        
        try:
            document.status = DocumentStatus.PROCESSING
            await db.flush()

            # 🔥 BORRAR DATOS ANTERIORES
            await self._delete_old_chunks_and_embeddings(db, document.id)

            text = await self._extract_text(file_path, document.file_type)
            
            if not text:
                raise ValueError("No text extracted")

            chunks = await self._create_chunks(db, document, text)

            embeddings_created = await self.rag_service.process_document_chunks(db, chunks)

            document.status = DocumentStatus.PROCESSED
            await db.flush()

            return len(chunks), embeddings_created

        except Exception:
            logger.exception("FATAL ERROR PROCESSING DOCUMENT")
            await db.rollback()
            document.status = DocumentStatus.ERROR
            await db.flush()
            raise
    
    async def _extract_text(self, file_path: str, file_type: str) -> str:
        """Extrae texto de un archivo según su tipo."""
        try:
            if file_type.lower() == "pdf":
                return await self._extract_from_pdf(file_path)
            elif file_type.lower() in ["docx", "doc"]:
                return await self._extract_from_docx(file_path)
            elif file_type.lower() == "txt":
                return await self._extract_from_txt(file_path)
            else:
                logger.warning("Unsupported file type", file_type=file_type)
                return ""
        except Exception as e:
            logger.error("Error extracting text", file_path=file_path, error=str(e))
            return ""

    async def _extract_from_pdf(self, file_path: str) -> str:
        try:
            import PyPDF2
            text = ""

            with open(file_path, "rb") as file:
                pdf_reader = PyPDF2.PdfReader(file)

                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"

            return text.strip()

        except Exception as e:
            logger.error("Error extracting from PDF", error=str(e))
            return ""
    
    async def _extract_from_docx(self, file_path: str) -> str:
        """Extrae texto de un DOCX."""
        try:
            from docx import Document as DocxDocument
            doc = DocxDocument(file_path)
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
            return text
        except Exception as e:
            logger.error("Error extracting from DOCX", error=str(e))
            return ""
    
    async def _extract_from_txt(self, file_path: str) -> str:
        """Extrae texto de un archivo de texto plano."""
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                return file.read()
        except Exception as e:
            logger.error("Error extracting from TXT", error=str(e))
            return ""
    
    async def _create_chunks(
        self,
        db: AsyncSession,
        document: Document,
        text: str
    ) -> List[DocumentChunk]:
        """Crea chunks del texto."""

        chunks = []
        start = 0
        chunk_index = 0

        while start < len(text):

            end = start + self.chunk_size
            chunk_text = text[start:end]

            # 🔥 evitar chunks vacíos
            if not chunk_text.strip():
                break

            # Intentar cortar en punto lógico
            if end < len(text):
                last_period = chunk_text.rfind(".")
                last_newline = chunk_text.rfind("\n")
                cut_point = max(last_period, last_newline)

                if cut_point > self.chunk_size * 0.5:
                    chunk_text = chunk_text[:cut_point + 1]
                    end = start + len(chunk_text)

            chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=chunk_index,
                content=chunk_text.strip(),
                metadata={
                    "start_char": start,
                    "end_char": end,
                    "length": len(chunk_text)
                }
            )

            db.add(chunk)
            chunks.append(chunk)

            start = end - self.chunk_overlap
            chunk_index += 1

        await db.flush()  # 🔥 mejor que commit aquí
        return chunks

    async def _delete_old_chunks_and_embeddings(self, db: AsyncSession, document_id: int):
        """Borra chunks y embeddings anteriores."""
        # Borrar embeddings
        await db.execute(
            delete(Embedding).where(
                Embedding.chunk_id.in_(
                    select(DocumentChunk.id).where(
                        DocumentChunk.document_id == document_id
                    )
                )
            )
        )

        # Borrar chunks
        await db.execute(
            delete(DocumentChunk).where(
                DocumentChunk.document_id == document_id
            )
        )

        await db.flush()

