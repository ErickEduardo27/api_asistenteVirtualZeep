from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.chat import ChatRequest
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.auth import get_current_active_user
from app.models.user import User

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

