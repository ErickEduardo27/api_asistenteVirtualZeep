from typing import AsyncIterator, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.models.conversation import Conversation, Message
from app.models.user import User
from app.services.llm import LLMService
from app.services.rag import RAGService

logger = structlog.get_logger()


class ChatOrchestrator:
    """Orquestador principal para el chat con streaming y RAG."""
    
    def __init__(self):
        self.llm_service = LLMService()
        self.rag_service = RAGService()
    
    async def stream_chat_response(
        self,
        db: AsyncSession,
        user: User,
        user_message: str,
        conversation_id: Optional[int] = None,
        use_rag: bool = True,
        temperature: float = 0.7,
        max_tokens: Optional[int] = 1000
    ) -> AsyncIterator[dict]:
        """
        Genera una respuesta de chat con streaming.
        
        Args:
            db: Sesión de base de datos
            user: Usuario actual
            user_message: Mensaje del usuario
            conversation_id: ID de conversación existente o None para nueva
            use_rag: Si usar RAG para contexto
            temperature: Temperatura para el LLM
            max_tokens: Máximo de tokens
            
        Yields:
            Diccionarios con eventos del stream
        """
        try:
            # Obtener o crear conversación
            conversation = await self._get_or_create_conversation(
                db, user, conversation_id
            )
            
            # Guardar mensaje del usuario
            user_msg = Message(
                conversation_id=conversation.id,
                role="user",
                content=user_message
            )
            db.add(user_msg)
            await db.commit()
            
            # Recuperar contexto RAG si está habilitado
            rag_context = None
            if use_rag:
                rag_context = await self.rag_service.retrieve_context(
                    db, user_message, user_id=user.id
                )
            
            # Construir historial de mensajes
            messages = await self._build_message_history(db, conversation.id)
            messages.append({"role": "user", "content": user_message})
            
            # Generar respuesta con streaming
            assistant_content = ""
            async for chunk in self.llm_service.stream_chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                use_rag=use_rag,
                rag_context=rag_context
            ):
                assistant_content += chunk
                yield {
                    "event": "token",
                    "data": chunk,
                    "conversation_id": conversation.id
                }
            
            # Guardar respuesta del asistente
            assistant_msg = Message(
                conversation_id=conversation.id,
                role="assistant",
                content=assistant_content,
                metadata={
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "use_rag": use_rag
                }
            )
            db.add(assistant_msg)
            await db.commit()
            
            # Evento final
            yield {
                "event": "done",
                "data": {
                    "conversation_id": conversation.id,
                    "message_id": assistant_msg.id
                }
            }
            
        except Exception as e:
            logger.error("Error in chat orchestrator", error=str(e))
            yield {
                "event": "error",
                "data": {"error": str(e)}
            }
    
    async def _get_or_create_conversation(
        self,
        db: AsyncSession,
        user: User,
        conversation_id: Optional[int]
    ) -> Conversation:
        """Obtiene una conversación existente o crea una nueva."""
        if conversation_id:
            result = await db.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user.id
                )
            )
            conversation = result.scalar_one_or_none()
            if conversation:
                return conversation
        
        # Crear nueva conversación
        conversation = Conversation(
            user_id=user.id,
            title="Nueva conversación"
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
        return conversation
    
    async def _build_message_history(
        self,
        db: AsyncSession,
        conversation_id: int,
        limit: int = 10
    ) -> list[dict]:
        """Construye el historial de mensajes para el LLM."""
        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = result.scalars().all()
        
        # Invertir para tener orden cronológico
        messages = list(reversed(messages))
        
        # Convertir a formato OpenAI
        formatted = []
        for msg in messages:
            formatted.append({
                "role": msg.role,
                "content": msg.content
            })
        
        return formatted

