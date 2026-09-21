"""Vector derivado de una versión de norma; la fuente de verdad sigue siendo normas."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from app.models.shared.base import Base


class NormaEmbedding(Base):
    __tablename__ = "norma_embeddings"
    norma_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("normas.id"), primary_key=True)
    modelo: Mapped[str]
    modelo_digest: Mapped[str]
    contenido_hash: Mapped[str]
    dimension: Mapped[int]
    vector: Mapped[list[float]] = mapped_column(Vector(1024).with_variant(JSON(), "sqlite"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc))
