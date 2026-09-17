import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.shared.base import Base

class ComparacionDocumentos(Base):
    __tablename__ = "comparaciones_documentos"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"), index=True)
    documento_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documentos.id"))
    documento_b_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documentos.id"))
    diferencias: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
