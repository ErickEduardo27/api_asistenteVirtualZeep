from typing import AsyncIterator, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timezone
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

        try:
            # 🔹 Obtener o crear conversación
            conversation = await self._get_or_create_conversation(
                db, user, conversation_id
            )

            # 🔹 Guardar mensaje usuario (SIN commit)
            user_msg = Message(
                conversation_id=conversation.id,
                role="user",
                content=user_message
            )
            db.add(user_msg)
            await db.flush()  # 🔥 SOLO flush

            # 🔹 RAG
            rag_context = None
            if use_rag:
                rag_context = await self.rag_service.retrieve_context(
                    db, user_message, user_id=user.id
                )

            # 🔹 Historial
            messages = await self._build_message_history(db, conversation.id)
            messages.append({"role": "user", "content": user_message})

            assistant_content = ""

            # 🔥 STREAMING
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

            # 🔹 Guardar respuesta asistente
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
            
            # Actualizar updated_at de la conversación
            await db.execute(
                update(Conversation)
                .where(Conversation.id == conversation.id)
                .values(updated_at=datetime.now(timezone.utc))
            )

            # 🔥 UN SOLO COMMIT AL FINAL
            await db.commit()

            yield {
                "event": "done",
                "data": {
                    "conversation_id": conversation.id,
                    "message_id": assistant_msg.id
                }
            }

        except Exception as e:
            await db.rollback()
            logger.error("Error in chat orchestrator", exc_info=True)

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

