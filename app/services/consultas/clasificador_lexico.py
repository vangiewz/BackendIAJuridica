import re
from dataclasses import dataclass
from typing import Optional

from app.models.shared.enums import AreaJuridica
from app.services.consultas.normalizacion import normalizar
from app.services.consultas.diccionario_areas import DICCIONARIO

UMBRAL_MINIMO = 1.0

@dataclass(frozen=True)
class Clasificacion:
    area: Optional[AreaJuridica]
    puntaje: float
    terminos_detectados: tuple[str, ...]
    puntajes_por_area: dict[str, float]

def _crear_patron(texto: str) -> re.Pattern:
    """
    Crea un patron de regex para un termino, permitiendo la forma singular
    o plural ('s' o 'es') al final de cada palabra.
    """
    palabras = texto.split()
    partes = [rf"{re.escape(p)}(?:es|s)?" for p in palabras]
    # \b asegura que sea coincidencia de palabra completa
    return re.compile(r"\b" + r"\s+".join(partes) + r"\b")

_PATRONES = {
    area: [(termino, _crear_patron(termino.texto)) for termino in terminos]
    for area, terminos in DICCIONARIO.items()
}

def _puntuar(texto_norm: str) -> tuple[dict[str, float], list[tuple[int, str, AreaJuridica]]]:
    """Puntaje de cada area y los terminos que aparecieron, con su posicion en la consulta."""
    puntajes = {area.value: 0.0 for area in AreaJuridica}
    encontrados: list[tuple[int, str, AreaJuridica]] = []

    for area, area_patrones in _PATRONES.items():
        for termino, patron in area_patrones:
            match = patron.search(texto_norm)
            # Un termino suma una sola vez aunque se repita: si no, una consulta
            # repetitiva gana por volumen y no por pertinencia.
            if match:
                puntajes[area.value] += termino.peso
                encontrados.append((match.start(), termino.texto, area))

    return puntajes, encontrados


def _terminos_del_area(encontrados, area: AreaJuridica) -> tuple[str, ...]:
    """Terminos del area ganadora, en el orden en que el usuario los escribio."""
    propios = [(pos, txt) for pos, txt, a in encontrados if a == area]
    propios.sort(key=lambda x: x[0])
    return tuple(txt for _, txt in propios)


def clasificar(texto: str) -> Clasificacion:
    """Area juridica de una consulta, con los terminos que dispararon la decision."""
    texto_norm = normalizar(texto)
    vacio = {area.value: 0.0 for area in AreaJuridica}
    if not texto_norm.strip():
        return Clasificacion(None, 0.0, (), vacio)

    puntajes, encontrados = _puntuar(texto_norm)
    area_val = max(puntajes, key=puntajes.get)
    mayor = puntajes[area_val]

    # Por debajo del umbral no se clasifica. Decir "no se" es correcto; elegir la menos
    # mala seria inventar una clasificacion que el usuario va a leer como afirmacion.
    if mayor < UMBRAL_MINIMO:
        return Clasificacion(None, 0.0, (), puntajes)

    ganadora = AreaJuridica(area_val)
    return Clasificacion(ganadora, mayor, _terminos_del_area(encontrados, ganadora), puntajes)
