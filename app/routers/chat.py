from fastapi import APIRouter, Depends, HTTPException, Query
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from typing import Optional
import structlog

from app.database import get_db
from app.schemas.chat import ChatRequest, MessageResponse, ConversationResponse, MessagesResponse
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.auth import get_current_active_user
from app.models.user import User
from app.models.conversation import Conversation, Message

logger = structlog.get_logger()

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/stream")
async def stream_chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Endpoint para chat con streaming.
    Retorna eventos SSE con los tokens generados.
    """
    orchestrator = ChatOrchestrator()
    
    async def event_generator():
        async for event in orchestrator.stream_chat_response(
            db=db,
            user=current_user,
            user_message=request.message,
            conversation_id=request.conversation_id,
            use_rag=request.use_rag,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        ):
            yield {
                "event": event.get("event", "message"),
                "data": event.get("data", "")
            }
    
    return EventSourceResponse(event_generator())


@router.get("/conversations", response_model=list[ConversationResponse])
async def get_conversations(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Obtiene todas las conversaciones del usuario ordenadas por fecha de actualización."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(desc(Conversation.updated_at))
    )
    conversations = result.scalars().all()
    
    # Construir respuesta con conteo de mensajes
    conversations_response = []
    for conv in conversations:
        # Obtener conteo de mensajes
        count_result = await db.execute(
            select(func.count(Message.id))
            .where(Message.conversation_id == conv.id)
        )
        message_count = count_result.scalar() or 0
        
        # Construir respuesta usando el schema
        conversations_response.append(
            ConversationResponse(
                id=conv.id,
                title=conv.title,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=message_count
            )
        )
    
    return conversations_response


@router.get("/conversations/{conversation_id}/messages", response_model=MessagesResponse)
async def get_messages(
    conversation_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Obtiene mensajes de una conversación con paginación."""
    # Verificar que la conversación pertenece al usuario
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id
        )
    )
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Obtener total de mensajes
    total_result = await db.execute(
        select(func.count(Message.id))
        .where(Message.conversation_id == conversation_id)
    )
    total = total_result.scalar() or 0
    
    # Calcular offset - para página 1, offset = 0 (últimos 10 mensajes)
    # Para página 2, offset = 10 (siguientes 10 más antiguos), etc.
    offset = (page - 1) * page_size
    
    # Obtener mensajes ordenados por fecha (más recientes primero)
    # NO invertimos, queremos los más recientes primero
    messages_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(desc(Message.created_at))
        .limit(page_size)
        .offset(offset)
    )
    messages = messages_result.scalars().all()
    
    # Los mensajes ya vienen ordenados: más recientes primero
    # has_more: si hay más mensajes después de esta página
    # Asegurar que siempre devolvamos exactamente page_size mensajes si hay suficientes
    has_more = total > (offset + len(messages))
    
    logger.info(
        "Retrieved messages",
        conversation_id=conversation_id,
        page=page,
        page_size=page_size,
        total=total,
        returned=len(messages),
        has_more=has_more
    )
    
    return MessagesResponse(
        messages=[MessageResponse.model_validate(msg) for msg in messages],
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
        conversation_id=conversation_id
    )


@router.get("/messages/latest", response_model=MessagesResponse)
async def get_latest_messages(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    # Obtener total de mensajes del usuario (todas sus conversaciones)
    total_result = await db.execute(
        select(func.count(Message.id))
        .join(Conversation)
        .where(Conversation.user_id == current_user.id)
    )
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size

    # Obtener mensajes más recientes del usuario
    messages_result = await db.execute(
        select(Message)
        .join(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(desc(Message.created_at))
        .limit(page_size)
        .offset(offset)
    )

    messages = messages_result.scalars().all()
    
        
    # Los mensajes ya vienen ordenados: más recientes primero
    # has_more: si hay más mensajes después de esta página
    # Asegurar que siempre devolvamos exactamente page_size mensajes si hay suficientes
    has_more = total > (offset + len(messages))
    
    logger.info(
        "Retrieved latest messages",
        conversation_id=latest_conversation.id,
        page=page,
        page_size=page_size,
        total=total,
        returned=len(messages),
        has_more=has_more
    )
    
    return MessagesResponse(
        messages=[MessageResponse.model_validate(msg) for msg in messages],
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
        conversation_id=latest_conversation.id
    )

