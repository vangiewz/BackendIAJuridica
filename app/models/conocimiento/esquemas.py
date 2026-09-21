from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.models.shared.enums import AreaJuridica, EstadoVigencia

class Ubicacion(BaseModel):
    libro: str | None = None
    parte: str | None = None
    titulo: str | None = None
    capitulo: str | None = None
    seccion: str | None = None

class ArticuloCorpus(BaseModel):
    """Un articulo listo para guardarse en el cliente. Sin `anterior`/`siguiente`:
    teniendo el corpus entero, el cliente los deduce y el servidor se ahorra un N+1."""
    id: UUID
    codigo: str
    articulo: str
    numero_articulo: int
    epigrafe: str | None
    texto: str
    area_juridica: AreaJuridica | None
    ubicacion: Ubicacion
    estado_vigencia: EstadoVigencia
    nota_vigencia: str | None
    fuente_nombre: str
    fuente_url: str
    version: int
    model_config = ConfigDict(from_attributes=True)

class VersionCorpus(BaseModel):
    codigo: str
    version: str          # huella opaca; si cambia, el cliente vuelve a bajar todo
    cantidad: int         # articulos activos
    generada_en: datetime

class PaginaCorpus(BaseModel):
    codigo: str
    version: str          # la misma huella; si no coincide con la que tiene, el cliente reinicia
    total: int
    desde: int            # desplazamiento pedido
    articulos: list[ArticuloCorpus]

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

class FuenteDisponible(BaseModel):
    """Una fuente del registro de perfiles, para que el admin elija sin adivinar."""
    clave: str
    codigo: str
    archivo: str
    total_esperado: int
    fuente_nombre: str
    fuente_url: str

class ReporteIngestaResponse(BaseModel):
    """Las mismas metricas que produce ReporteIngesta, mas el origen del archivo."""
    fuente: str
    codigo: str
    total_procesados: int
    insertadas: int
    actualizadas: int
    sin_cambios: int
    por_libro: dict[str, int]
    por_area: dict[str, int]
    origen: str            # 'subido' | 'incluido'

class NodoIndice(BaseModel):
    tipo: str
    nombre: str
    desde: int
    hasta: int
    cantidad: int
    numeros: list[int] = Field(default_factory=list)
    hijos: list["NodoIndice"] = Field(default_factory=list)

NodoIndice.model_rebuild()
