from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast
from sqlalchemy.orm import selectinload
from pgvector.sqlalchemy import Vector
""" from pgvector.sqlalchemy import cosine_distance """
from sqlalchemy import func
func
import structlog

from app.models.document import DocumentChunk, Document
from app.models.embedding import Embedding as EmbeddingModel
from app.services.llm import LLMService
from app.config import settings

logger = structlog.get_logger()


class RAGService:
    """Servicio para Retrieval-Augmented Generation."""
    
    def __init__(self):
        self.llm_service = LLMService()
        self.top_k = 5  # Número de chunks a recuperar
    
    async def search_similar_chunks(
        self,
        db: AsyncSession,
        query_embedding: list[float],
        user_id: Optional[int] = None,
        top_k: int = 5
    ) -> List[DocumentChunk]:
        """
        Busca chunks similares usando búsqueda vectorial.
        
        Args:
            db: Sesión de base de datos
            query_embedding: Embedding de la consulta
            user_id: ID del usuario para filtrar documentos
            top_k: Número de resultados a retornar
        """
        try:
            # Convertir embedding a formato pgvector
            embedding_vector = cast(query_embedding, Vector)
            
            # Construir la consulta de similitud
            query = select(
                DocumentChunk,
                func.cosine_distance(
                    EmbeddingModel.embedding,
                    embedding_vector
                ).label('distance')
            ).join(
                EmbeddingModel,
                DocumentChunk.id == EmbeddingModel.chunk_id
            ).join(
                Document,
                DocumentChunk.document_id == Document.id
            ).options(
                selectinload(DocumentChunk.document),
                selectinload(DocumentChunk.embedding)
            )
            
            # Filtrar por usuario si se proporciona
            if user_id:
                query = query.where(Document.user_id == user_id)
            
            # Ordenar por distancia (menor es mejor) y limitar
            query = query.order_by('distance').limit(top_k)
            
            result = await db.execute(query)
            rows = result.all()
            
            chunks = [row[0] for row in rows]
            logger.info("Found similar chunks", count=len(chunks))
            
            return chunks
            
        except Exception as e:
            logger.error("Error searching similar chunks", error=str(e))
            return []
    
    async def retrieve_context(
        self,
        db: AsyncSession,
        query: str,
        user_id: Optional[int] = None,
        top_k: int = 5
    ) -> Optional[str]:
        """
        Recupera contexto relevante para una consulta.
        
        Args:
            db: Sesión de base de datos
            query: Consulta del usuario
            user_id: ID del usuario
            top_k: Número de chunks a recuperar
        """
        try:
            # Crear embedding de la consulta
            query_embedding = await self.llm_service.create_embedding(query)
            
            # Buscar chunks similares
            chunks = await self.search_similar_chunks(
                db, query_embedding, user_id, top_k
            )
            
            if not chunks:
                return None
            
            # Construir contexto a partir de los chunks
            context_parts = []
            for chunk in chunks:
                doc_name = chunk.document.filename if chunk.document else "Unknown"
                context_parts.append(
                    f"[Documento: {doc_name}]\n{chunk.content}\n"
                )
            
            context = "\n---\n".join(context_parts)
            logger.info("Retrieved context", chunks_count=len(chunks))
            
            return context
            
        except Exception as e:
            logger.error("Error retrieving context", error=str(e))
            return None
    
    async def process_document_chunks(
        self,
        db: AsyncSession,
        chunks: List[DocumentChunk]
    ) -> int:
        """
        Procesa chunks de documento: crea embeddings y los guarda.
        
        Args:
            db: Sesión de base de datos
            chunks: Lista de chunks a procesar
        """
        embeddings_created = 0
        
        for chunk in chunks:
            try:
                # Verificar si ya existe un embedding
                result = await db.execute(
                    select(EmbeddingModel).where(EmbeddingModel.chunk_id == chunk.id)
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    continue
                
                # Crear embedding
                embedding_vector = await self.llm_service.create_embedding(chunk.content)
                
                # Guardar embedding
                embedding = EmbeddingModel(
                    chunk_id=chunk.id,
                    embedding=embedding_vector,
                    model=settings.embedding_model
                )
                
                db.add(embedding)
                embeddings_created += 1
                
            except Exception as e:
                logger.error(
                    "Error processing chunk",
                    chunk_id=chunk.id,
                    error=str(e)
                )
                continue
        
        await db.commit()
        logger.info("Processed document chunks", embeddings_created=embeddings_created)
        
        return embeddings_created

