import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, Enum as SAEnum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.shared.base import Base
from app.models.shared.enums import AreaJuridica, EstadoVigencia

class Norma(Base):
    __tablename__ = "normas"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    codigo: Mapped[str]
    articulo: Mapped[str]
    numero_articulo: Mapped[int] = mapped_column(index=True)
    epigrafe: Mapped[str | None] = mapped_column(nullable=True)
    texto: Mapped[str]

    # Ubicacion exacta dentro del codigo. De aca sale el area, no de un juicio del sistema.
    libro: Mapped[str | None] = mapped_column(nullable=True)
    parte: Mapped[str | None] = mapped_column(nullable=True)
    titulo: Mapped[str | None] = mapped_column(nullable=True)
    capitulo: Mapped[str | None] = mapped_column(nullable=True)
    seccion: Mapped[str | None] = mapped_column(nullable=True)

    area_juridica: Mapped[AreaJuridica | None] = mapped_column(
        SAEnum(AreaJuridica, name="areajuridica", values_callable=lambda e: [m.value for m in e]),
        nullable=True
    )

    # Procedencia: de donde salio este texto y cuando
    fuente_nombre: Mapped[str]
    fuente_url: Mapped[str]
    descargada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    estado_vigencia: Mapped[EstadoVigencia] = mapped_column(
        SAEnum(EstadoVigencia, name="estadovigencia", values_callable=lambda e: [m.value for m in e]),
        default=EstadoVigencia.SIN_VERIFICAR
    )
    nota_vigencia: Mapped[str | None] = mapped_column(nullable=True)

    version: Mapped[int] = mapped_column(default=1)
    vigente_desde: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    vigente_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activa: Mapped[bool] = mapped_column(default=True)
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("codigo", "numero_articulo", "version",
                         name="uq_normas_codigo_articulo_version"),
    )
