from dataclasses import dataclass
from typing import Callable
from app.models.shared.enums import TipoDocumento, SeveridadRiesgo
from app.services.documentos.segmentador_clausulas import Clausula
from app.services.documentos.extractor_entidades import Hallazgo

@dataclass(frozen=True)
class ContextoContrato:
    tipo: TipoDocumento
    texto: str
    texto_normalizado: str              # normalizar(texto), de services/shared
    clausulas: tuple[Clausula, ...]
    hallazgos: tuple[Hallazgo, ...]

@dataclass(frozen=True)
class Riesgo:
    codigo: str                         # 'CV-PRECIO-AUSENTE'
    titulo: str                         # una linea, en lenguaje del usuario
    severidad: SeveridadRiesgo          # ya existe en models/shared/enums.py
    articulos: tuple[int, ...]          # articulos del Codigo Civil que lo fundamentan
    explicacion: str                    # que establece la norma
    evidencia: str | None               # el fragmento que lo disparo
    inicio: int | None                  # offset de la evidencia en el texto
    clausula: int | None

Regla = Callable[[ContextoContrato], Riesgo | None]
