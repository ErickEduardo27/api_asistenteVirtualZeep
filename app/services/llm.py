from typing import AsyncIterator, Optional
import google.generativeai as genai
from app.config import settings
import structlog
import asyncio
import logging

logger = logging.getLogger(__name__)

class LLMService:
    """Servicio para interactuar con el LLM (Google Gemini)."""
    
    def __init__(self):
        if not settings.gemini_api_key:
            logger.warning("Gemini API key not configured")
            self.client = None
            self.model = None
        else:
            # Configurar Gemini
            genai.configure(api_key=settings.gemini_api_key)
            self.client = genai
            self.model = settings.llm_model
            logger.info("Gemini LLM service initialized", model=self.model)
    
    async def stream_chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: Optional[int] = 1000,
        use_rag: bool = True,
        rag_context: Optional[str] = None
    ) -> AsyncIterator[str]:

        if not self.client or not self.model:
            yield "Error: Gemini API key not configured"
            return

        try:
            # 🔹 Construir system prompt
            system_prompt = self._build_system_prompt(use_rag, rag_context)

            history = []
            last_user_message = None

            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")

                if role == "system":
                    continue
                elif role == "user":
                    if last_user_message is None:
                        last_user_message = content
                    else:
                        history.append({"role": "user", "parts": [content]})
                elif role == "assistant":
                    history.append({"role": "model", "parts": [content]})

            if last_user_message is None and history:
                last_user_message = history.pop(0)["parts"][0]

            # 🔹 Crear modelo
            model = genai.GenerativeModel(
                model_name=self.model,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens or 2048,
                )
            )

            if system_prompt:
                full_prompt = f"{system_prompt}\n\nUsuario: {last_user_message}"
            else:
                full_prompt = last_user_message or ""

            # 🔥 STREAMING REAL NO BLOQUEANTE
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue = asyncio.Queue()

            def worker():
                try:
                    if history:
                        chat = model.start_chat(history=history)
                        response = chat.send_message(full_prompt, stream=True)
                    else:
                        response = model.generate_content(full_prompt, stream=True)

                    for chunk in response:
                        if hasattr(chunk, "text") and chunk.text:
                            asyncio.run_coroutine_threadsafe(
                                queue.put(chunk.text),
                                loop
                            )

                except Exception as e:
                    asyncio.run_coroutine_threadsafe(
                        queue.put(f"Error: {str(e)}"),
                        loop
                    )
                finally:
                    asyncio.run_coroutine_threadsafe(
                        queue.put(None),
                        loop
                    )

            # Ejecutar todo el streaming en un hilo separado
            loop.run_in_executor(None, worker)

            # Consumir la queue sin bloquear el event loop
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item

        except Exception as e:
            logger.error("Error in LLM stream", exc_info=True)
            yield f"Error: {str(e)}"

    async def _stream_response(self, response):
    
        try:
            for chunk in response:
                if hasattr(chunk, "text") and chunk.text:
                    yield chunk.text
                elif hasattr(chunk, "parts"):
                    text_parts = []
                    for part in chunk.parts:
                        if hasattr(part, "text") and part.text:
                            text_parts.append(part.text)
                    if text_parts:
                        yield "".join(text_parts)

        except Exception as e:
            logger.error("Error streaming response", error=str(e))
            yield f"Error: {str(e)}"
    
    def _build_system_prompt(self, use_rag: bool, rag_context: Optional[str] = None) -> str:
        """Construye el prompt del sistema."""
        base_prompt = """Eres un asistente virtual inteligente y útil. 
Responde de manera clara, concisa y profesional."""
        
        if use_rag and rag_context:
            base_prompt += f"\n\nContexto adicional del documento:\n{rag_context}\n\n"
            base_prompt += "Usa este contexto para proporcionar respuestas más precisas y relevantes. Si la información no está en el contexto, indica que no tienes esa información disponible."
        
        return base_prompt
    
    async def create_embedding(self, text: str) -> list[float]:
        """Crea un embedding para el texto usando Gemini."""
        if not self.client:
            raise ValueError("Gemini API key not configured")
        
        try:
            # Gemini tiene un modelo específico para embeddings
            # Usar el modelo de embedding de Gemini
            result = await asyncio.to_thread(
                genai.embed_content,
                model=settings.embedding_model,
                content=text,
                task_type="retrieval_document"  # Para documentos, usar "retrieval_query" para consultas
            )
            
            if result and 'embedding' in result:
                return result['embedding']
            elif isinstance(result, dict) and 'embedding' in result:
                return result['embedding']
            else:
                raise ValueError(f"No embedding returned from Gemini. Result: {result}")
                
        except Exception as e:
            logger.error("Error creating embedding", error=str(e), text_preview=text[:50])
            raise
