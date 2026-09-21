import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Enum as SAEnum, JSON, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.shared.base import Base
from app.models.shared.enums import AreaJuridica, EstadoProceso

class Consulta(Base):
    __tablename__ = "consultas"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"), index=True)
    # Documento sobre el que se hizo la consulta, si la hubo sobre alguno. Las consultas
    # generales no tienen ninguno; borrar el documento no borra la consulta.
    documento_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documentos.id", ondelete="SET NULL"), nullable=True, index=True)
    texto: Mapped[str]
    area_juridica: Mapped[AreaJuridica | None] = mapped_column(
        SAEnum(AreaJuridica, name="areajuridica", values_callable=lambda e: [m.value for m in e]),
        nullable=True
    )
    respuesta: Mapped[str | None] = mapped_column(nullable=True)
    etapa_ia: Mapped[str | None] = mapped_column(nullable=True)
    ia_error: Mapped[str | None] = mapped_column(nullable=True)
    estado: Mapped[EstadoProceso] = mapped_column(
        SAEnum(EstadoProceso, name="estadoproceso", values_callable=lambda e: [m.value for m in e]),
        default=EstadoProceso.PENDIENTE
    )
    terminos_detectados: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    version_diccionario: Mapped[str | None] = mapped_column(nullable=True)
    client_op_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("usuario_id", "client_op_id", name="uq_consultas_usuario_client_op"),
    )
