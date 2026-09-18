from dataclasses import dataclass
from app.models.shared.enums import TipoDocumento
from app.services.contratos.catalogo_riesgos import Riesgo, ContextoContrato
from app.services.contratos.reglas_comunes import REGLAS_COMUNES
from app.services.contratos.reglas_compraventa import REGLAS_COMPRAVENTA
from app.services.contratos.reglas_arrendamiento import REGLAS_ARRENDAMIENTO
from app.services.contratos.reglas_prestamo import REGLAS_PRESTAMO
from app.services.documentos.extractor_entidades import extraer
from app.services.shared.normalizacion import normalizar

from app.services.documentos.segmentador_clausulas import Clausula
from app.services.documentos.extractor_entidades import Hallazgo

@dataclass(frozen=True)
class Analisis:
    riesgos: tuple[Riesgo, ...]
    reglas_evaluadas: int
    tipo: TipoDocumento
    clausulas: tuple[Clausula, ...]
    hallazgos: tuple[Hallazgo, ...]
    parrafo_partes: str | None

def analizar(texto: str, tipo: TipoDocumento) -> Analisis:
    """Corre las reglas que aplican al tipo. Cada riesgo cita su articulo."""
    texto_norm = normalizar(texto)
    extraccion = extraer(texto)
    
    ctx = ContextoContrato(
        tipo=tipo,
        texto=texto,
        texto_normalizado=texto_norm,
        clausulas=extraccion.clausulas,
        hallazgos=extraccion.hallazgos
    )
    
    reglas = list(REGLAS_COMUNES)
    if tipo == TipoDocumento.COMPRAVENTA:
        reglas.extend(REGLAS_COMPRAVENTA)
    elif tipo == TipoDocumento.ARRENDAMIENTO:
        reglas.extend(REGLAS_ARRENDAMIENTO)
    elif tipo == TipoDocumento.PRESTAMO:
        reglas.extend(REGLAS_PRESTAMO)
        
    riesgos = []
    for regla in reglas:
        riesgo = regla(ctx)
        if riesgo is not None:
            riesgos.append(riesgo)
            
    def severidad_score(s: str) -> int:
        if s == 'alta': return 0
        if s == 'media': return 1
        return 2
        
    riesgos.sort(key=lambda r: (severidad_score(r.severidad.value), r.inicio if r.inicio is not None else float('inf')))
    
    return Analisis(
        riesgos=tuple(riesgos),
        reglas_evaluadas=len(reglas),
        tipo=tipo,
        clausulas=extraccion.clausulas,
        hallazgos=extraccion.hallazgos,
        parrafo_partes=extraccion.parrafo_partes
    )
