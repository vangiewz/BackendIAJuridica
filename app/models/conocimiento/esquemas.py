from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.models.shared.enums import AreaJuridica, EstadoVigencia

class Ubicacion(BaseModel):
    libro: str | None = None
    parte: str | None = None
    titulo: str | None = None
    capitulo: str | None = None
    seccion: str | None = None

class NormaResumen(BaseModel):
    id: UUID
    codigo: str
    articulo: str
    numero_articulo: int
    epigrafe: str | None
    fragmento: str
    area_juridica: AreaJuridica | None
    libro: str | None
    relevancia: float
    estado_vigencia: EstadoVigencia
    model_config = ConfigDict(from_attributes=True)

class ResultadoBusqueda(BaseModel):
    consulta: str
    total: int
    resultados: list[NormaResumen]

class ArticuloDetalle(BaseModel):
    id: UUID
    codigo: str
    articulo: str
    numero_articulo: int
    epigrafe: str | None
    texto: str
    area_juridica: AreaJuridica | None
    ubicacion: Ubicacion
    anterior: int | None
    siguiente: int | None
    estado_vigencia: EstadoVigencia
    nota_vigencia: str | None
    fuente_nombre: str
    fuente_url: str
    model_config = ConfigDict(from_attributes=True)

class NodoIndice(BaseModel):
    tipo: str
    nombre: str
    desde: int
    hasta: int
    cantidad: int
    numeros: list[int] = Field(default_factory=list)
    hijos: list["NodoIndice"] = Field(default_factory=list)

NodoIndice.model_rebuild()
