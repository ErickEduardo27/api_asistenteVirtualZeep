import asyncio
from typing import List,Optional
import os
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk, DocumentStatus
from app.models.embedding import Embedding as EmbeddingModel
from app.services.llm import LLMService
from app.config import settings
from sqlalchemy import select, cast
from sqlalchemy.orm import selectinload
from pgvector.sqlalchemy import Vector
from sqlalchemy import func


logger = structlog.get_logger()


class DocumentProcessor:
    """Procesa documentos: extracción de texto, chunking y creación de embeddings."""

    def __init__(self):
        self.rag_service = RAGService()
        self.chunk_size = 1000  # caracteres por chunk
        self.chunk_overlap = 200

    async def process_document(
        self,
        db: AsyncSession,
        document: Document,
        file_path: str
    ) -> tuple[int, int]:
        """Procesa un documento completo y genera chunks + embeddings."""
        try:
            # Marcar documento en procesamiento
            document.status = DocumentStatus.PROCESSING
            await db.commit()

            # Extraer texto
            text_chunks = await self._extract_text_chunks(file_path, document.file_type)

            if not text_chunks:
                document.status = DocumentStatus.ERROR
                await db.commit()
                return 0, 0

            # Crear chunks en DB
            chunks = await self._create_chunks(db, document, text_chunks)

            # Crear embeddings concurrentemente
            embeddings_created = await self.rag_service.process_document_chunks_concurrent(db, chunks)

            # Marcar documento como procesado
            document.status = DocumentStatus.PROCESSED
            await db.commit()

            logger.info(
                "Document processed",
                document_id=document.id,
                chunks=len(chunks),
                embeddings=embeddings_created
            )

            return len(chunks), embeddings_created

        except Exception as e:
            logger.error("Error processing document", document_id=document.id, error=str(e))
            document.status = DocumentStatus.ERROR
            await db.commit()
            return 0, 0

    async def _extract_text_chunks(self, file_path: str, file_type: str) -> List[str]:
        """Extrae texto del archivo y devuelve una lista de textos por página/chunk base."""
        try:
            if file_type.lower() == "pdf":
                return await self._extract_from_pdf(file_path)
            elif file_type.lower() in ["docx", "doc"]:
                text = await self._extract_from_docx(file_path)
                return [text] if text else []
            elif file_type.lower() == "txt":
                text = await self._extract_from_txt(file_path)
                return [text] if text else []
            else:
                logger.warning("Unsupported file type", file_type=file_type)
                return []
        except Exception as e:
            logger.error("Error extracting text", file_path=file_path, error=str(e))
            return []

    async def _extract_from_pdf(self, file_path: str) -> List[str]:
        """Extrae texto de un PDF, página por página para procesar grandes archivos."""
        try:
            import PyPDF2
            text_chunks = []
            with open(file_path, "rb") as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_chunks.append(page_text)
            return text_chunks
        except Exception as e:
            logger.error("Error extracting from PDF", error=str(e))
            return []

    async def _extract_from_docx(self, file_path: str) -> str:
        try:
            from docx import Document as DocxDocument
            doc = DocxDocument(file_path)
            text = "\n".join([p.text for p in doc.paragraphs])
            return text
        except Exception as e:
            logger.error("Error extracting from DOCX", error=str(e))
            return ""

    async def _extract_from_txt(self, file_path: str) -> str:
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
        text_chunks: List[str]
    ) -> List[DocumentChunk]:
        """Divide el texto en chunks manejables y los guarda en la BD."""
        chunks = []
        chunk_index = 0

        for text in text_chunks:
            start = 0
            while start < len(text):
                end = start + self.chunk_size
                chunk_text = text[start:end]

                # Cortar en un punto lógico
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
                    meta={"start_char": start, "end_char": end, "length": len(chunk_text)}
                )
                chunks.append(chunk)
                chunk_index += 1

                start = end - self.chunk_overlap

        # Bulk insert en la DB
        db.add_all(chunks)
        await db.commit()
        return chunks


# ==========================
# RAGService optimizado
# ==========================


class RAGService:
    """Servicio optimizado para Retrieval-Augmented Generation (RAG)."""

    def __init__(self):
        self.llm_service = LLMService()
        self.top_k = 5  # Número de chunks a recuperar

    # --------------------------
    # Búsqueda vectorial
    # --------------------------
    async def search_similar_chunks(
        self,
        db: AsyncSession,
        query_embedding: list[float],
        user_id: Optional[int] = None,
        top_k: int = 5
    ) -> List[DocumentChunk]:
        """Busca chunks similares usando PGVector y cosine_distance."""
        try:
            embedding_vector = cast(query_embedding, Vector)

            query = (
                select(
                    DocumentChunk,
                    func.cosine_distance(EmbeddingModel.embedding, embedding_vector).label("distance")
                )
                .join(EmbeddingModel, DocumentChunk.id == EmbeddingModel.chunk_id)
                .join(Document, DocumentChunk.document_id == Document.id)
                .options(
                    selectinload(DocumentChunk.document),
                    selectinload(DocumentChunk.embedding)
                )
            )

            if user_id:
                query = query.where(Document.user_id == user_id)

            query = query.order_by("distance").limit(top_k)

            result = await db.execute(query)
            rows = result.all()
            chunks = [row[0] for row in rows]

            logger.info("Found similar chunks", count=len(chunks))
            return chunks

        except Exception as e:
            logger.error("Error searching similar chunks", error=str(e))
            return []

    # --------------------------
    # Recuperar contexto para RAG
    # --------------------------
    async def retrieve_context(
        self,
        db: AsyncSession,
        query: str,
        user_id: Optional[int] = None,
        top_k: int = 5
    ) -> Optional[str]:
        """Recupera el contexto relevante para una consulta del usuario."""
        try:
            query_embedding = await self.llm_service.create_embedding(query)

            chunks = await self.search_similar_chunks(
                db, query_embedding, user_id, top_k
            )

            if not chunks:
                logger.info("No relevant chunks found")
                return None

            context_parts = [
                f"[Documento: {chunk.document.filename if chunk.document else 'Unknown'}]\n{chunk.content}\n"
                for chunk in chunks
            ]

            context = "\n---\n".join(context_parts)

            # ✔ Forma correcta
            logger.info("Retrieved %s chunks for RAG context", len(chunks))

            return context

        except Exception:
            # ✔ Mucho mejor
            logger.exception("Error retrieving context")
            return None

    # --------------------------
    # Crear embeddings concurrentes
    # --------------------------
    async def process_document_chunks(
        self,
        db: AsyncSession,
        chunks: List[DocumentChunk]
    ) -> int:
        """
        Crea embeddings concurrentemente para todos los chunks que no tengan embedding.
        No hace commit. El commit lo debe hacer el proceso principal.
        """

        embeddings_created = 0
        tasks = []
        chunk_map = []

        # Filtrar solo chunks sin embedding existente en DB
        for chunk in chunks:
            # verificar si ya existe embedding para este chunk
            result = await db.execute(
                select(EmbeddingModel).where(
                    EmbeddingModel.chunk_id == chunk.id
                )
            )
            existing = result.scalar_one_or_none()

            if not existing:
                tasks.append(self.llm_service.create_embedding(chunk.content))
                chunk_map.append(chunk)

        if not tasks:
            return 0

        # Ejecutar concurrentemente, pero tolerante a errores
        vectors = await asyncio.gather(*tasks, return_exceptions=True)

        for chunk, vector in zip(chunk_map, vectors):

            # Si hubo error en este embedding, lo logeamos y seguimos
            if isinstance(vector, Exception):
                logger.error(
                    "Embedding failed",
                    chunk_id=chunk.id,
                    error=str(vector)
                )
                continue

            embedding = EmbeddingModel(
                chunk_id=chunk.id,
                embedding=vector,
                model=settings.embedding_model
            )

            db.add(embedding)
            embeddings_created += 1

        logger.info(
            "Processed document chunks",
            embeddings_created=embeddings_created
        )

        return embeddings_created
