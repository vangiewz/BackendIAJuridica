import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.models.shared.base import Base
from app.models.shared.enums import TipoDocumento

class DocumentoGenerado(Base):
    __tablename__ = "documentos_generados"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"), index=True)
    tipo_documento: Mapped[TipoDocumento] = mapped_column(
        SAEnum(TipoDocumento, name="tipodocumento", values_callable=lambda e: [m.value for m in e])
    )
    contenido: Mapped[str]
    version: Mapped[int] = mapped_column(default=1)
    documento_padre_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documentos_generados.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
