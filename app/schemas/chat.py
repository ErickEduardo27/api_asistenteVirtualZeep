from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None
    use_rag: bool = True
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1000


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    conversation_id: int
    message: MessageResponse
    tokens_used: Optional[int] = None


class ConversationResponse(BaseModel):
    id: int
    title: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    message_count: Optional[int] = 0

    class Config:
        from_attributes = True


class MessagesResponse(BaseModel):
    messages: List[MessageResponse]
    total: int
    page: int
    page_size: int
    has_more: bool
    conversation_id: Optional[int] = None  # ID de la conversación de estos mensajes