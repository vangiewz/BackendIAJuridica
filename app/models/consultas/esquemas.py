from datetime import datetime
from typing import Any
from uuid import UUID
from pydantic import BaseModel, Field

from app.models.shared.enums import AreaJuridica, EstadoProceso, EstadoVigencia
from app.models.ia.esquemas import RespuestaJuridicaIA

class ConsultaRequest(BaseModel):
    texto: str = Field(min_length=3, max_length=2000)
    # Documento activo de la conversacion, si lo hay. La pertenencia se comprueba en el
    # backend contra el usuario del token: no se confia en este id.
    documento_id: UUID | None = None
    client_op_id: UUID | None = None

class FuenteLegalResponse(BaseModel):
    norma_id: UUID | None = None
    version: int | None = None
    utilizada: bool = False
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
    documento_id: UUID | None = None
    documento_nombre: str | None = None
    # Que hizo el sistema con la frase: consulta_general, consulta_documento,
    # guardar_documento, analizar_documento o consulta_documento_normativa.
    intencion: str | None = None
    area_juridica: AreaJuridica | None
    terminos_detectados: list[str]
    puntajes_por_area: dict[str, float]
    fuentes: list[FuenteLegalResponse]
    respuesta: RespuestaJuridicaIA | None
    etapa_ia: str | None = None
    ia_error: str | None = None
    estado: EstadoProceso
    creada_en: datetime

class ItemHistorial(BaseModel):
    id: UUID
    texto: str
    area_juridica: AreaJuridica | None
    cantidad_fuentes: int
    documento_nombre: str | None = None
    creada_en: datetime

class HistorialResponse(BaseModel):
    total: int
    items: list[ItemHistorial]
