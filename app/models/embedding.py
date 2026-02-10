from sqlalchemy import Column, Integer, ForeignKey, String
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.database import Base


class Embedding(Base):
    __tablename__ = "embeddings"

    id = Column(Integer, primary_key=True, index=True)
    chunk_id = Column(Integer, ForeignKey("document_chunks.id"), unique=True, nullable=False)
    embedding = Column(Vector(1536), nullable=False)  # 1536 para OpenAI embeddings
    model = Column(String, nullable=False)  # Modelo usado para generar el embedding

    # Relaciones
    chunk = relationship("DocumentChunk", back_populates="embedding")

