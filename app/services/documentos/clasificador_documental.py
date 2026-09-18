import re
from dataclasses import dataclass
from app.models.shared.enums import TipoDocumento
from app.services.shared.normalizacion import normalizar
from app.services.documentos.diccionario_tipos import DICCIONARIO

UMBRAL_MINIMO_TIPO = 3.0

@dataclass(frozen=True)
class ClasificacionDocumental:
    tipo: TipoDocumento                  # nunca None: cae a OTRO
    puntaje: float
    terminos_detectados: tuple[str, ...]
    puntajes_por_tipo: dict[str, float]

def _crear_patron(texto: str) -> re.Pattern:
    palabras = texto.split()
    partes = [rf"{re.escape(p)}(?:es|s)?" for p in palabras]
    return re.compile(r"\b" + r"\s+".join(partes) + r"\b")

_PATRONES = {
    tipo: [(termino, _crear_patron(termino.texto)) for termino in terminos]
    for tipo, terminos in DICCIONARIO.items()
}

def _puntuar(texto_norm: str) -> tuple[dict[str, float], list[tuple[int, str, TipoDocumento]]]:
    puntajes = {tipo.value: 0.0 for tipo in TipoDocumento}
    encontrados: list[tuple[int, str, TipoDocumento]] = []

    for tipo, tipo_patrones in _PATRONES.items():
        for termino, patron in tipo_patrones:
            match = patron.search(texto_norm)
            if match:
                puntajes[tipo.value] += termino.peso
                encontrados.append((match.start(), termino.texto, tipo))

    return puntajes, encontrados

def _terminos_del_tipo(encontrados, tipo: TipoDocumento) -> tuple[str, ...]:
    propios = [(pos, txt) for pos, txt, t in encontrados if t == tipo]
    propios.sort(key=lambda x: x[0])
    return tuple(txt for _, txt in propios)

def clasificar_documento(texto: str) -> ClasificacionDocumental:
    """Tipo de documento segun los terminos que aparecen. Expone cuales lo dispararon."""
    texto_norm = normalizar(texto)
    puntajes_iniciales = {tipo.value: 0.0 for tipo in TipoDocumento}
    
    if not texto_norm.strip():
        return ClasificacionDocumental(TipoDocumento.OTRO, 0.0, (), puntajes_iniciales)

    puntajes, encontrados = _puntuar(texto_norm)
    
    # Excluir OTRO de la busqueda del maximo, ya que no tiene terminos y su puntaje es 0
    tipos_validos = [t for t in TipoDocumento if t != TipoDocumento.OTRO]
    tipo_val = max(tipos_validos, key=lambda x: puntajes[x.value])
    mayor = puntajes[tipo_val.value]

    if mayor < UMBRAL_MINIMO_TIPO:
        return ClasificacionDocumental(TipoDocumento.OTRO, 0.0, (), puntajes)

    return ClasificacionDocumental(tipo_val, mayor, _terminos_del_tipo(encontrados, tipo_val), puntajes)
