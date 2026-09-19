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

class ComparacionRequest(BaseModel):
    documento_a_id: UUID
    documento_b_id: UUID

class DiferenciaResponse(BaseModel):
    tipo: str                    # 'agregado' | 'eliminado' | 'modificado'
    ubicacion: str
    texto_anterior: str | None
    texto_nuevo: str | None
    explicacion: str
    clausula: int | None

class ItemComparacion(BaseModel):
    """Fila del historial de comparaciones: lo justo para volver a abrirla."""
    id: UUID
    documento_a_id: UUID
    documento_b_id: UUID
    nombre_a: str
    nombre_b: str
    estrategia: str
    cantidad_cambios: int
    creada_en: datetime

class ComparacionesResponse(BaseModel):
    total: int
    items: list[ItemComparacion]

class ComparacionResponse(BaseModel):
    id: UUID
    documento_a_id: UUID
    documento_b_id: UUID
    nombre_a: str
    nombre_b: str
    estrategia: str              # 'clausulas' | 'texto'
    cantidad_cambios: int
    diferencias: list[DiferenciaResponse]
    creada_en: datetime
