import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.models.shared.base import Base
from app.models.shared.enums import TipoDocumento, EstadoProceso

class Documento(Base):
    __tablename__ = "documentos"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"), index=True)
    nombre_archivo: Mapped[str]
    tipo_documento: Mapped[TipoDocumento | None] = mapped_column(
        SAEnum(TipoDocumento, name="tipodocumento", values_callable=lambda e: [m.value for m in e]),
        nullable=True
    )
    texto_extraido: Mapped[str | None] = mapped_column(nullable=True)
    estado: Mapped[EstadoProceso] = mapped_column(
        SAEnum(EstadoProceso, name="estadoproceso", values_callable=lambda e: [m.value for m in e]),
        default=EstadoProceso.PENDIENTE
    )
    subido_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
