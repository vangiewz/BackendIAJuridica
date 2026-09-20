"""Que la especificación no diga más de lo que dijo el usuario.

El modelo tiende a "mejorar" la petición: ante «mostrame nombre, montos, plazos y
cantidad de riesgos de mis préstamos» respondía agrupando por mes y contando riesgos,
que es un reporte distinto del que se pidió.

El prompt pide fidelidad, pero un prompt es una recomendación. Acá se comprueba contra
el texto real de la petición y se quita lo que el usuario no pidió. Es un trinquete en
una sola dirección: esto solo *saca* agrupaciones, agregaciones o gráficos añadidos de
más, nunca agrega nada. Si la petición sí los pide, la respuesta del modelo se respeta
tal cual.
"""
import re
import unicodedata

from app.models.reportes.esquemas import EspecificacionReporte
from app.services.reportes.catalogo import ENTIDADES, Entidad

# Verbos de agrupar y de calcular. "cantidad" no está: «cantidad de riesgos» es el
# nombre de una columna por fila, no una petición de agregar (por eso fallaba el caso
# original). "cuant" sí, porque «cuántos» siempre pregunta por un total.
MARCAS_AGRUPAR = ("agrupa", "agrupá", "distribuci", "desglos", "clasificad")
MARCAS_AGREGAR = ("cuant", "promedio", "media de", "suma", "sumá", "total",
                  "contar", "conteo", "maximo", "minimo")

MARCAS_VISUALIZACION = (
    # La torta va antes que las barras: "gráfico circular" contiene las dos ideas.
    ("torta", ("torta", "circular", "pastel", "pie chart", "dona", "anillo")),
    ("barras", ("barra", "grafico", "grafica", "chart", "histograma")),
    ("resumen", ("resumime", "resumi ", "resumilo", "un resumen", "como resumen",
                 "en resumen", "resumen de los resultados")),
    ("tabla", ("tabla", "listado", "listame", "en filas")),
)

MARCAS_EXPORTACION = (
    ("xlsx", ("excel", "xlsx", "planilla", "hoja de calculo", "spreadsheet")),
    ("pptx", ("powerpoint", "power point", "pptx", "diapositiva", "presentacion",
              "presentación", "ppt")),
    ("docx", ("word", "docx", "documento de texto")),
    ("pdf", ("pdf",)),
)


def normalizar(texto: str) -> str:
    plano = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in plano if not unicodedata.combining(c))


def _alias_agrupables(entidad: Entidad) -> set[str]:
    """Cómo puede nombrar el usuario un campo por el que sí se puede agrupar."""
    alias: set[str] = set()
    for nombre, campo in entidad.campos.items():
        if not campo.agrupable:
            continue
        alias.add(normalizar(nombre).replace("_", " "))
        etiqueta = normalizar(campo.etiqueta)
        alias.add(etiqueta)
        primera = etiqueta.split(" ")[0]
        if len(primera) >= 3:
            alias.add(primera)
    return alias


def pide_agrupar(peticion: str, entidad: Entidad) -> bool:
    """Si la frase realmente pide agrupar: un verbo de agrupar o «por <campo agrupable>»."""
    texto = normalizar(peticion)
    if any(marca in texto for marca in MARCAS_AGRUPAR):
        return True
    return any(re.search(r"\b(?:por|segun)\s+(?:cada\s+)?" + re.escape(alias) + r"\b", texto)
               for alias in _alias_agrupables(entidad))


def pide_agregar(peticion: str) -> bool:
    texto = normalizar(peticion)
    return any(marca in texto for marca in MARCAS_AGREGAR)


def detectar_visualizacion(peticion: str) -> str:
    """El formato pedido en la frase, o "" si no se mencionó ninguno."""
    texto = normalizar(peticion)
    for forma, marcas in MARCAS_VISUALIZACION:
        if any(marca in texto for marca in marcas):
            return forma
    return ""


def detectar_exportacion(peticion: str) -> str:
    """El archivo pedido en la frase ("...y exportalo a Excel"), o "" si no pidió archivo.

    Se resuelve acá y no en el modelo porque es una decisión léxica exacta: nombrar
    Excel o PDF no admite interpretación, y así una descarga nunca se dispara sola.
    """
    texto = normalizar(peticion)
    for formato, marcas in MARCAS_EXPORTACION:
        if any(marca in texto for marca in marcas):
            return formato
    return ""


def ajustar_a_lo_pedido(spec: EspecificacionReporte, peticion: str,
                        actual: EspecificacionReporte | None = None) -> EspecificacionReporte:
    """Devuelve la especificación sin lo que la petición no pidió."""
    entidad = ENTIDADES.get((spec.entidad or "").strip().lower())
    if entidad is None:
        return spec

    cambios: dict = {}
    # En un ajuste sobre un reporte existente ("ahora ordenalo al revés") lo que ya
    # estaba agrupado sigue agrupado: se compara contra el reporte previo, no contra cero.
    previa_agrupacion = list(actual.agrupacion) if actual else []
    previas_agregaciones = list(actual.agregaciones) if actual else []

    if not pide_agrupar(peticion, entidad) and list(spec.agrupacion) != previa_agrupacion:
        cambios["agrupacion"] = previa_agrupacion

    # Un reporte agrupado necesita sí o sí una agregación, así que la del modelo se
    # respeta. Lo que no puede pasar es que un listado de detalle, sin agrupación ni
    # verbo de cálculo, se colapse en un único número: ese era el error original.
    agrupacion_final = cambios.get("agrupacion", list(spec.agrupacion))
    if (not agrupacion_final and not pide_agregar(peticion)
            and list(spec.agregaciones) != previas_agregaciones):
        cambios["agregaciones"] = previas_agregaciones

    pedida = detectar_visualizacion(peticion)
    if pedida:
        cambios["visualizacion"] = pedida
    elif spec.visualizacion != "tabla":
        # Sin gráfico pedido, un reporte no se convierte en gráfico solo.
        cambios["visualizacion"] = actual.visualizacion if actual else "tabla"

    # El formato de archivo lo decide el texto, no el modelo.
    cambios["exportacion"] = detectar_exportacion(peticion)

    return spec.model_copy(update=cambios) if cambios else spec
