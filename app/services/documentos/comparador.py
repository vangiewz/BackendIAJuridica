import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.services.documentos.segmentador_clausulas import segmentar, Clausula
from app.services.documentos.patrones import (
    MONTO_BOLIVIANOS, MONTO_DOLARES, FECHA_NUMERICA, FECHA_LARGA, PLAZO
)

TIPO_AGREGADO = "agregado"
TIPO_ELIMINADO = "eliminado"
TIPO_MODIFICADO = "modificado"

ESTRATEGIA_CLAUSULAS = "clausulas"
ESTRATEGIA_TEXTO = "texto"

# Un parrafo sin estructura puede ser enorme. Se recorta para no guardar un documento
# entero dentro de una fila de diferencias ni mandarlo al telefono; el corte es visible.
MAXIMO_FRAGMENTO = 1200


@dataclass(frozen=True)
class Diferencia:
    tipo: str                    # 'agregado' | 'eliminado' | 'modificado'
    ubicacion: str               # 'Cláusula SEGUNDA' o 'Párrafo 3'
    texto_anterior: str | None   # None cuando el contenido es nuevo
    texto_nuevo: str | None      # None cuando el contenido se elimino
    explicacion: str
    clausula: int | None         # orden de la clausula, cuando la diferencia es de una


@dataclass(frozen=True)
class Comparacion:
    estrategia: str
    diferencias: tuple[Diferencia, ...]


def _recortar(texto: str) -> str:
    limpio = texto.strip()
    if len(limpio) <= MAXIMO_FRAGMENTO:
        return limpio
    return limpio[:MAXIMO_FRAGMENTO].rstrip() + "…"


def _comparable(texto: str) -> str:
    """Para decidir si dos textos son el mismo: el espaciado no es un cambio."""
    return " ".join(texto.split())


def _matches(texto: str, patrones) -> list[str]:
    encontrados: list[tuple[int, str]] = []
    for patron in patrones:
        for match in patron.finditer(texto):
            encontrados.append((match.start(), match.group(0)))
    encontrados.sort(key=lambda par: par[0])
    return [texto for _, texto in encontrados]


def _cambio_puntual(anterior: str, nuevo: str, patrones) -> tuple[str, str] | None:
    """
    El primer valor que cambio, solo si se pueden emparejar con seguridad.

    Si una version tiene mas montos que la otra no hay emparejamiento confiable:
    se devuelve None y la explicacion queda neutral en vez de afirmar algo falso.
    """
    antes = _matches(anterior, patrones)
    despues = _matches(nuevo, patrones)
    if antes == despues or len(antes) != len(despues):
        return None
    for a, b in zip(antes, despues):
        if a != b:
            return a, b
    return None


# El orden importa: se informa el primer tipo de dato que cambio.
_CATEGORIAS = (
    ("El monto cambió de {antes} a {despues}.", (MONTO_BOLIVIANOS, MONTO_DOLARES)),
    ("El plazo cambió de {antes} a {despues}.", (PLAZO,)),
    ("La fecha cambió de {antes} a {despues}.", (FECHA_NUMERICA, FECHA_LARGA)),
)


def _explicar_modificacion(anterior: str, nuevo: str) -> str:
    """
    Explicacion derivada del texto, nunca interpretada.

    Solo se nombra el dato que cambio cuando se lo puede identificar con los mismos
    patrones que ya usa la extraccion. Si no, se dice que cambio el contenido y nada mas.
    """
    for plantilla, patrones in _CATEGORIAS:
        cambio = _cambio_puntual(anterior, nuevo, patrones)
        if cambio:
            return plantilla.format(antes=cambio[0], despues=cambio[1])
    return "El contenido de esta sección fue modificado."


def _etiqueta(clausula: Clausula) -> str:
    return f"Cláusula {clausula.ordinal}" if clausula.ordinal else f"Cláusula {clausula.orden}"


def _contenido(clausula: Clausula) -> str:
    """
    Todo el texto de la clausula.

    El segmentador deja la primera linea entera en `encabezado` y solo el resto en
    `texto`: en una clausula de una sola linea el cuerpo queda vacio, asi que comparar
    `texto` a secas no detectaria ningun cambio.
    """
    encabezado = clausula.encabezado.strip()
    cuerpo = clausula.texto.strip()
    return f"{encabezado}\n{cuerpo}" if cuerpo else encabezado


def _indexar(clausulas: list[Clausula]) -> list[tuple[str, Clausula]]:
    """
    Clave de emparejamiento por clausula. El ordinal ya viene normalizado por el
    segmentador ('PRIMERA', 'SEGUNDA', '1'), asi que dos documentos con el mismo
    ordinal se emparejan aunque el texto haya cambiado por completo. Un ordinal
    repetido dentro del mismo documento se desambigua para no perder una clausula.
    """
    claves: list[tuple[str, Clausula]] = []
    vistas: dict[str, int] = {}
    for clausula in clausulas:
        base = clausula.ordinal or f"#{clausula.orden}"
        vistas[base] = vistas.get(base, 0) + 1
        clave = base if vistas[base] == 1 else f"{base} ({vistas[base]})"
        claves.append((clave, clausula))
    return claves


def _diferencia_clausula(tipo: str, clausula: Clausula, otra: Clausula | None) -> Diferencia:
    if tipo == TIPO_AGREGADO:
        return Diferencia(
            tipo=TIPO_AGREGADO,
            ubicacion=_etiqueta(clausula),
            texto_anterior=None,
            texto_nuevo=_recortar(_contenido(clausula)),
            explicacion=f"Se agregó la {_etiqueta(clausula).lower()}.",
            clausula=clausula.orden,
        )
    if tipo == TIPO_ELIMINADO:
        return Diferencia(
            tipo=TIPO_ELIMINADO,
            ubicacion=_etiqueta(clausula),
            texto_anterior=_recortar(_contenido(clausula)),
            texto_nuevo=None,
            explicacion=f"Se eliminó la {_etiqueta(clausula).lower()}.",
            clausula=clausula.orden,
        )

    assert otra is not None
    anterior = _contenido(clausula)
    nuevo = _contenido(otra)
    return Diferencia(
        tipo=TIPO_MODIFICADO,
        ubicacion=_etiqueta(otra),
        texto_anterior=_recortar(anterior),
        texto_nuevo=_recortar(nuevo),
        explicacion=_explicar_modificacion(anterior, nuevo),
        clausula=otra.orden,
    )


def _comparar_clausulas(clausulas_a: list[Clausula], clausulas_b: list[Clausula]) -> list[Diferencia]:
    indice_a = _indexar(clausulas_a)
    indice_b = _indexar(clausulas_b)
    claves_a = [clave for clave, _ in indice_a]
    claves_b = [clave for clave, _ in indice_b]

    diferencias: list[Diferencia] = []
    matcher = SequenceMatcher(None, claves_a, claves_b, autojunk=False)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            # Mismo ordinal en los dos documentos: se compara el contenido.
            for desplazamiento in range(i2 - i1):
                clausula_a = indice_a[i1 + desplazamiento][1]
                clausula_b = indice_b[j1 + desplazamiento][1]
                if _comparable(_contenido(clausula_a)) != _comparable(_contenido(clausula_b)):
                    diferencias.append(_diferencia_clausula(TIPO_MODIFICADO, clausula_a, clausula_b))
            continue

        # 'replace' son ordinales distintos a un lado y al otro: emparejarlos seria
        # adivinar, asi que se informa lo que desaparecio y lo que aparecio.
        if tag in ("delete", "replace"):
            for posicion in range(i1, i2):
                diferencias.append(_diferencia_clausula(TIPO_ELIMINADO, indice_a[posicion][1], None))
        if tag in ("insert", "replace"):
            for posicion in range(j1, j2):
                diferencias.append(_diferencia_clausula(TIPO_AGREGADO, indice_b[posicion][1], None))

    return diferencias


def _bloques(texto: str) -> list[str]:
    """Parrafos del documento; si no hay parrafos separados, se cae a las lineas."""
    parrafos = [b.strip() for b in re.split(r"\n\s*\n", texto) if b.strip()]
    if len(parrafos) > 1:
        return parrafos
    return [linea.strip() for linea in texto.splitlines() if linea.strip()]


def _comparar_texto(texto_a: str, texto_b: str) -> list[Diferencia]:
    bloques_a = _bloques(texto_a)
    bloques_b = _bloques(texto_b)
    normalizados_a = [_comparable(b) for b in bloques_a]
    normalizados_b = [_comparable(b) for b in bloques_b]

    diferencias: list[Diferencia] = []
    matcher = SequenceMatcher(None, normalizados_a, normalizados_b, autojunk=False)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue

        if tag == "replace":
            # Se emparejan de a uno mientras haya pareja; el resto es agregado o eliminado.
            comunes = min(i2 - i1, j2 - j1)
            for desplazamiento in range(comunes):
                anterior = bloques_a[i1 + desplazamiento]
                nuevo = bloques_b[j1 + desplazamiento]
                diferencias.append(Diferencia(
                    tipo=TIPO_MODIFICADO,
                    ubicacion=f"Párrafo {j1 + desplazamiento + 1}",
                    texto_anterior=_recortar(anterior),
                    texto_nuevo=_recortar(nuevo),
                    explicacion=_explicar_modificacion(anterior, nuevo),
                    clausula=None,
                ))
            for posicion in range(i1 + comunes, i2):
                diferencias.append(_diferencia_bloque(TIPO_ELIMINADO, bloques_a[posicion], posicion))
            for posicion in range(j1 + comunes, j2):
                diferencias.append(_diferencia_bloque(TIPO_AGREGADO, bloques_b[posicion], posicion))
            continue

        if tag == "delete":
            for posicion in range(i1, i2):
                diferencias.append(_diferencia_bloque(TIPO_ELIMINADO, bloques_a[posicion], posicion))
        elif tag == "insert":
            for posicion in range(j1, j2):
                diferencias.append(_diferencia_bloque(TIPO_AGREGADO, bloques_b[posicion], posicion))

    return diferencias


def _diferencia_bloque(tipo: str, texto: str, posicion: int) -> Diferencia:
    if tipo == TIPO_AGREGADO:
        return Diferencia(
            tipo=TIPO_AGREGADO,
            ubicacion=f"Párrafo {posicion + 1}",
            texto_anterior=None,
            texto_nuevo=_recortar(texto),
            explicacion="Se agregó contenido que no estaba en el primer documento.",
            clausula=None,
        )
    return Diferencia(
        tipo=TIPO_ELIMINADO,
        ubicacion=f"Párrafo {posicion + 1}",
        texto_anterior=_recortar(texto),
        texto_nuevo=None,
        explicacion="Se eliminó contenido que estaba en el primer documento.",
        clausula=None,
    )


def comparar(texto_a: str, texto_b: str) -> Comparacion:
    """
    Diferencias entre dos versiones de un documento, sin modelo generativo.

    Se compara por clausulas cuando los dos documentos tienen estructura reconocible,
    porque el ordinal da una ubicacion que el usuario puede buscar en el papel. Si a
    alguno no se le reconocen clausulas, se cae a comparar parrafos.
    """
    clausulas_a = segmentar(texto_a)
    clausulas_b = segmentar(texto_b)

    if clausulas_a and clausulas_b:
        return Comparacion(
            estrategia=ESTRATEGIA_CLAUSULAS,
            diferencias=tuple(_comparar_clausulas(clausulas_a, clausulas_b)),
        )

    return Comparacion(
        estrategia=ESTRATEGIA_TEXTO,
        diferencias=tuple(_comparar_texto(texto_a, texto_b)),
    )
