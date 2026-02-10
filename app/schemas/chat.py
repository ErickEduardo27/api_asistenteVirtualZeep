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

