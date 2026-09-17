import uuid
from enum import Enum
from datetime import datetime, timezone
from sqlalchemy import DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.models.shared.base import Base

class RolUsuario(str, Enum):
    """Roles de usuario en el sistema."""
    CIUDADANO = "ciudadano"
    PROFESIONAL = "profesional"
    ADMINISTRADOR = "administrador"

class Usuario(Base):
    """Entidad que representa a un usuario en el sistema."""
    __tablename__ = "usuarios"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    nombre: Mapped[str]
    password_hash: Mapped[str]
    # values_callable fuerza a Postgres a guardar los VALORES ("ciudadano") y no los
    # nombres de los miembros ("CIUDADANO"), que es el default de SQLAlchemy. Sin esto
    # la API expone "ciudadano" mientras la base guarda "CIUDADANO", y un WHERE directo falla.
    rol: Mapped[RolUsuario] = mapped_column(
        SAEnum(RolUsuario, name="rolusuario", values_callable=lambda e: [m.value for m in e]),
        default=RolUsuario.CIUDADANO,
    )
    activo: Mapped[bool] = mapped_column(default=True)
    # timezone=True es necesario: sin el, Postgres guarda "timestamp without time zone"
    # y se pierde el offset del datetime UTC que se le pasa.
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
