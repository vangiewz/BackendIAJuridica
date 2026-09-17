import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.models.shared.base import Base
from app.models.shared.enums import AreaJuridica

class Norma(Base):
    __tablename__ = "normas"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    codigo: Mapped[str]
    articulo: Mapped[str] = mapped_column(index=True)
    titulo: Mapped[str | None] = mapped_column(nullable=True)
    texto: Mapped[str]
    area_juridica: Mapped[AreaJuridica] = mapped_column(
        SAEnum(AreaJuridica, name="areajuridica", values_callable=lambda e: [m.value for m in e])
    )
    version: Mapped[int] = mapped_column(default=1)
    vigente_desde: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    vigente_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activa: Mapped[bool] = mapped_column(default=True)
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
