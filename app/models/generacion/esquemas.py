from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.ia.esquemas import FuenteIA
from app.models.shared.enums import TipoDocumento


# Los únicos formatos en que se puede bajar un borrador. No se admite ningún otro.
FormatoBorrador = Literal["docx", "pdf"]


class InterpretacionRequest(BaseModel):
    """Un pedido en lenguaje natural, solo o sobre un formulario ya empezado.

    Sin `tipo_documento` el sistema lo deduce del texto. Con `datos` el texto se usa
    para completar ese formulario, no para empezar uno nuevo.
    """
    texto: str = Field(min_length=3, max_length=2000)
    tipo_documento: TipoDocumento | None = None
    datos: dict[str, str] = Field(default_factory=dict)


class DatoDetectado(BaseModel):
    campo: str
    etiqueta: str
    valor: str
    evidencia: str = ""


class ConflictoDato(BaseModel):
    """Un dato del texto que choca con uno que ya estaba cargado. Nunca se aplica solo."""
    campo: str
    etiqueta: str
    valor_actual: str
    valor_detectado: str
    evidencia: str = ""
    # True cuando la frase pedía el cambio expresamente ("cambiá el precio a…").
    explicito: bool = False


class CampoPendiente(BaseModel):
    clave: str
    etiqueta: str
    obligatorio: bool


class ProblemaCampo(BaseModel):
    """Un campo del formulario que el usuario debe revisar, y por qué."""
    clave: str
    etiqueta: str
    mensaje: str
    ejemplo: str = ""
    # error: no sirve y hay que corregirlo para generar. aviso: probablemente dé problemas.
    nivel: Literal["error", "aviso"] = "error"


class InterpretacionResponse(BaseModel):
    tipo_documento: TipoDocumento | None = None
    # El formulario ya combinado: lo que había más lo detectado que no genera conflicto.
    datos: dict[str, str] = Field(default_factory=dict)
    detectados: list[DatoDetectado] = Field(default_factory=list)
    conflictos: list[ConflictoDato] = Field(default_factory=list)
    campos_pendientes: list[CampoPendiente] = Field(default_factory=list)
    # Campos que el modelo propuso pero no estaban literalmente en el texto: se
    # descartan y se informan, nunca se cargan.
    descartados: list[str] = Field(default_factory=list)
    # Cuando hace falta que el usuario elija el tipo antes de seguir.
    requiere_tipo: bool = False
    mensaje: str = ""
    # Campos que quedaron con algo que no sirve («hoy» como fecha, una sigla como lugar): se avisan
    # apenas se interpreta, antes de intentar generar.
    problemas: list[ProblemaCampo] = Field(default_factory=list)


class GeneracionRequest(BaseModel):
    tipo_documento: TipoDocumento
    datos: dict[str, str] = Field(default_factory=dict)


class RevisionRequest(BaseModel):
    """HU-15: un cambio pedido en lenguaje natural, datos corregidos, o ambos."""
    instruccion: str | None = Field(default=None, max_length=500)
    datos: dict[str, str] | None = None
    contenido: str | None = Field(default=None, max_length=40000)


class CampoPlantilla(BaseModel):
    clave: str
    etiqueta: str
    obligatorio: bool
    # Cómo se escribe este dato: la pantalla lo muestra en gris dentro del campo vacío.
    ejemplo: str = ""


class PlantillaResponse(BaseModel):
    tipo_documento: TipoDocumento
    titulo: str
    campos: list[CampoPlantilla]
    clausulas: list[str]


class DocumentoGeneradoResponse(BaseModel):
    id: UUID
    tipo_documento: TipoDocumento
    contenido: str
    version: int
    documento_padre_id: UUID | None
    campos_faltantes: list[str] = []
    fuentes: list[FuenteIA] = []
    ia_error: str | None = None
    creado_en: datetime


class VersionResumen(BaseModel):
    id: UUID
    version: int
    documento_padre_id: UUID | None
    creado_en: datetime
