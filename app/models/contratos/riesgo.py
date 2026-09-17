import uuid
from sqlalchemy import ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.models.shared.base import Base
from app.models.shared.enums import SeveridadRiesgo

class RiesgoContractual(Base):
    __tablename__ = "riesgos_contractuales"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    analisis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analisis_documentos.id", ondelete="CASCADE"), index=True)
    descripcion: Mapped[str]
    motivo: Mapped[str]
    severidad: Mapped[SeveridadRiesgo] = mapped_column(
        SAEnum(SeveridadRiesgo, name="severidadriesgo", values_callable=lambda e: [m.value for m in e])
    )
    clausula_referencia: Mapped[str | None] = mapped_column(nullable=True)
