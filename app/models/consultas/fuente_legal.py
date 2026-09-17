import uuid
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.shared.base import Base

class FuenteLegal(Base):
    __tablename__ = "fuentes_legales"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    consulta_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("consultas.id", ondelete="CASCADE"), index=True)
    norma_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("normas.id"), nullable=True)
    articulo: Mapped[str]
    texto_citado: Mapped[str]
    relevancia: Mapped[float]
    orden: Mapped[int]
