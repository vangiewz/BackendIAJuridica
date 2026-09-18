from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from app.models.shared.enums import TipoDocumento, EstadoProceso

class DocumentoResponse(BaseModel):
    id: UUID
    nombre_archivo: str
    tipo_documento: TipoDocumento | None
    terminos_detectados: list[str]
    cantidad_caracteres: int | None
    estado: EstadoProceso
    motivo_fallo: str | None
    subido_en: datetime

class DocumentoDetalle(DocumentoResponse):
    texto_extraido: str | None

class ItemDocumento(BaseModel):
    id: UUID
    nombre_archivo: str
    tipo_documento: TipoDocumento | None
    estado: EstadoProceso
    subido_en: datetime

class DocumentosResponse(BaseModel):
    total: int
    items: list[ItemDocumento]
