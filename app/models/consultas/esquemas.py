from datetime import datetime
from typing import Any
from uuid import UUID
from pydantic import BaseModel, Field

from app.models.shared.enums import AreaJuridica, EstadoProceso, EstadoVigencia

class ConsultaRequest(BaseModel):
    texto: str = Field(min_length=3, max_length=2000)

class FuenteLegalResponse(BaseModel):
    articulo: str
    numero_articulo: int
    codigo: str
    epigrafe: str | None
    texto_citado: str
    relevancia: float
    orden: int
    estado_vigencia: EstadoVigencia
    fuente_url: str

class ConsultaResponse(BaseModel):
    id: UUID
    texto: str
    area_juridica: AreaJuridica | None
    terminos_detectados: list[str]
    puntajes_por_area: dict[str, float]
    fuentes: list[FuenteLegalResponse]
    respuesta: None
    estado: EstadoProceso
    creada_en: datetime

class ItemHistorial(BaseModel):
    id: UUID
    texto: str
    area_juridica: AreaJuridica | None
    cantidad_fuentes: int
    creada_en: datetime

class HistorialResponse(BaseModel):
    total: int
    items: list[ItemHistorial]
