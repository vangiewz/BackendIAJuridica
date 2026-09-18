import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.shared.base import Base

class AnalisisDocumento(Base):
    __tablename__ = "analisis_documentos"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    documento_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documentos.id", ondelete="CASCADE"), index=True)
    resumen: Mapped[str | None] = mapped_column(nullable=True)
    partes: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    obligaciones: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    fechas: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    montos: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    observaciones: Mapped[str | None] = mapped_column(nullable=True)
    hallazgos: Mapped[list] = mapped_column(JSON().with_variant(JSONB, "postgresql"), server_default="[]")
    reglas_evaluadas: Mapped[int] = mapped_column(server_default="0")
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
