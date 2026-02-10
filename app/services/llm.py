from typing import AsyncIterator, Optional
from openai import AsyncOpenAI
from app.config import settings
import structlog

logger = structlog.get_logger()


class LLMService:
    """Servicio para interactuar con el LLM (OpenAI)."""
    
    def __init__(self):
        if not settings.openai_api_key:
            logger.warning("OpenAI API key not configured")
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.model = settings.llm_model
    
    async def stream_chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: Optional[int] = 1000,
        use_rag: bool = True,
        rag_context: Optional[str] = None
    ) -> AsyncIterator[str]:
        """
        Genera una respuesta del LLM con streaming.
        
        Args:
            messages: Lista de mensajes en formato OpenAI
            temperature: Temperatura para la generación
            max_tokens: Máximo de tokens a generar
            use_rag: Si usar contexto RAG
            rag_context: Contexto adicional del RAG
        """
        if not self.client:
            yield "Error: OpenAI API key not configured"
            return
        
        # Construir el prompt final con contexto RAG si está disponible
        system_message = {
            "role": "system",
            "content": self._build_system_prompt(use_rag, rag_context)
        }
        
        # Insertar system message al inicio si no existe
        formatted_messages = [system_message]
        for msg in messages:
            if msg.get("role") != "system":
                formatted_messages.append(msg)
        
        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=formatted_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )
            
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            logger.error("Error in LLM stream", error=str(e))
            yield f"Error: {str(e)}"
    
    def _build_system_prompt(self, use_rag: bool, rag_context: Optional[str] = None) -> str:
        """Construye el prompt del sistema."""
        base_prompt = """Eres un asistente virtual inteligente y útil. 
Responde de manera clara, concisa y profesional."""
        
        if use_rag and rag_context:
            base_prompt += f"\n\nContexto adicional del documento:\n{rag_context}\n\n"
            base_prompt += "Usa este contexto para proporcionar respuestas más precisas y relevantes."
        
        return base_prompt
    
    async def create_embedding(self, text: str) -> list[float]:
        """Crea un embedding para el texto."""
        if not self.client:
            raise ValueError("OpenAI API key not configured")
        
        try:
            response = await self.client.embeddings.create(
                model=settings.embedding_model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error("Error creating embedding", error=str(e))
            raise

