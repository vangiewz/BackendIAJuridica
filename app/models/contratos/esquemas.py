from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from app.models.shared.enums import SeveridadRiesgo, TipoDocumento

class RiesgoResponse(BaseModel):
    codigo_regla: str
    titulo: str
    severidad: SeveridadRiesgo
    articulos: list[int]
    explicacion: str
    evidencia: str | None
    inicio: int | None
    clausula: int | None

class ClausulaResponse(BaseModel):
    orden: int
    encabezado: str
    texto: str
    inicio: int
    fin: int

class HallazgoResponse(BaseModel):
    tipo: str
    texto: str
    inicio: int
    fin: int
    clausula: int | None

class AnalisisResponse(BaseModel):
    id: UUID
    documento_id: UUID
    tipo_documento: TipoDocumento
    clausulas: list[ClausulaResponse]
    hallazgos: list[HallazgoResponse]
    parrafo_partes: str | None
    riesgos: list[RiesgoResponse]
    reglas_evaluadas: int
    resumen: None
    observaciones: None
    creado_en: datetime
