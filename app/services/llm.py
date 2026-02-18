from typing import AsyncIterator, Optional
from google import genai
from google.genai import types

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
            # Crear cliente nuevo del SDK moderno
            self.client = genai.Client(api_key=settings.gemini_api_key)
            self.model = settings.llm_model  # ej: "gemini-1.5-flash"
            logger.info("Gemini LLM service initialized", model=self.model)
    
    async def stream_chat(
        self,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: Optional[int] = 512,
        use_rag: bool = True,
        rag_context: Optional[str] = None
    ) -> AsyncIterator[str]:
        print("Se imprime --------------------------------------------------------------")
        # 🔒 BLOQUEAR si no hay contexto en modo RAG
        if use_rag and (not rag_context or not rag_context.strip()):
            yield "Lo siento, no encontré información sobre eso en los documentos disponibles."
            return
            print("No hay contexto en modo RAG")
        print("SÍ hay contexto en modo RAG")
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
            """ model = genai.GenerativeModel(
                model_name=self.model,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens or 512,
                )
            ) """

            if system_prompt:
                full_prompt = f"{system_prompt}\n\nUsuario: {last_user_message}"
            else:
                full_prompt = last_user_message or ""

            # 🔥 STREAMING REAL NO BLOQUEANTE
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue = asyncio.Queue()

            def worker():
                try:
                    response = self.client.models.generate_content_stream(
                        model=self.model,
                        contents=full_prompt,
                        config=types.GenerateContentConfig(
                            temperature=temperature,
                            max_output_tokens=max_tokens or 512,
                        )
                    )

                    for chunk in response:
                        if chunk.text:
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
    
    from typing import Optional

    def _build_system_prompt(self, use_rag: bool, rag_context: Optional[str] = None) -> str:
        """Construye el prompt del sistema."""

        if use_rag and rag_context:
            return f"""
                Eres un asistente amable y profesional.

                Usa únicamente la información del CONTEXTO para responder.
                No uses conocimiento externo ni inventes datos.

                Si la respuesta no está en el CONTEXTO, responde exactamente:
                "Lo siento, no encontré información sobre eso en los documentos disponibles."

                CONTEXTO:
                {rag_context}
                """
        else:
            return """
            Eres un asistente virtual inteligente y útil.
            Responde de manera clara, concisa y profesional.
            """
    
    async def create_embedding(self, text: str) -> list[float]:
        """Crea un embedding para el texto usando Gemini con 1536 dimensiones."""
        if not self.client:
            raise ValueError("Gemini API key not configured")

        try:
            result = await asyncio.to_thread(
                self.client.models.embed_content,
                model=settings.embedding_model,
                contents=text,
                config=types.EmbedContentConfig(
                    output_dimensionality=1536
                )
            )

            embedding = result.embeddings[0].values

            print(len(embedding))
            return embedding

        except Exception as e:
            logger.error("Error creating embedding: %s", str(e))
            raise