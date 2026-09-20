from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from typing import Literal
from app.models.shared.enums import SeveridadRiesgo, TipoDocumento
from app.models.ia.esquemas import FuenteIA, ObservacionIA

class RiesgoResponse(BaseModel):
    # El origen viaja con el dato: la interfaz nunca tiene que adivinar quién lo produjo.
    origen: Literal["reglas"] = "reglas"
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
    # Producido por IA sobre las cláusulas, los riesgos ya detectados y la normativa recuperada.
    resumen: str | None = None
    observaciones: list[ObservacionIA] = []
    fuentes_ia: list[FuenteIA] = []
    ia_error: str | None = None
    creado_en: datetime
