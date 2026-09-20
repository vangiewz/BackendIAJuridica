"""Lo que todos los exportadores necesitan ver igual.

El archivo tiene que decir exactamente lo que dice la pantalla, así que la forma de la
tabla, del gráfico y de los metadatos se calcula una sola vez aquí, a partir del
`ReporteResultado` ya generado. Ningún exportador vuelve a consultar la base ni al
modelo de lenguaje.
"""
from datetime import datetime, timezone

from app.models.reportes.esquemas import ReporteResultado
from app.services.reportes.fechas import ZONA_BOLIVIA
from app.services.shared.normalizacion import sanear_nombre_archivo

VACIO = "—"
MAXIMO_TEXTO = 300


def formatear(valor, tipo: str) -> str:
    """El mismo texto que muestra la pantalla para esa celda."""
    if valor is None or valor == "":
        return VACIO
    if tipo == "fecha" and isinstance(valor, str):
        try:
            fecha = datetime.fromisoformat(valor)
        except ValueError:
            return str(valor)
        return fecha.astimezone(ZONA_BOLIVIA).strftime("%d/%m/%Y")
    if isinstance(valor, float):
        return f"{round(valor, 2):g}"
    texto = str(valor)
    return texto if len(texto) <= MAXIMO_TEXTO else texto[:MAXIMO_TEXTO].rstrip() + "…"


def encabezados(reporte: ReporteResultado) -> list[str]:
    return [columna.etiqueta for columna in reporte.columnas]


def filas_de_texto(reporte: ReporteResultado) -> list[list[str]]:
    return [[formatear(fila.get(columna.clave), columna.tipo)
             for columna in reporte.columnas]
            for fila in reporte.filas]


def valor_numerico(valor) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def datos_de_grafico(reporte: ReporteResultado):
    """(etiquetas, valores, título del valor) si el reporte se puede graficar."""
    etiqueta = next((c for c in reporte.columnas if c.tipo != "numero"), None)
    valor = next((c for c in reporte.columnas if c.tipo == "numero"), None)
    if etiqueta is None or valor is None or not reporte.filas:
        return None
    etiquetas = [formatear(fila.get(etiqueta.clave), etiqueta.tipo) for fila in reporte.filas]
    valores = [valor_numerico(fila.get(valor.clave)) for fila in reporte.filas]
    return etiquetas, valores, valor.etiqueta


def generado_en() -> str:
    return datetime.now(timezone.utc).astimezone(ZONA_BOLIVIA).strftime("%d/%m/%Y %H:%M")


def metadatos(reporte: ReporteResultado) -> list[tuple[str, str]]:
    """Ficha del reporte: de dónde salió y con qué condiciones."""
    datos = [
        ("Generado", generado_en()),
        ("Entidad", reporte.entidad_etiqueta),
        ("Resultados", str(reporte.total)),
        ("Presentación", reporte.visualizacion),
    ]
    if reporte.peticion:
        datos.insert(0, ("Petición", reporte.peticion))
    if reporte.filtros_aplicados:
        datos.append(("Filtros aplicados", " · ".join(reporte.filtros_aplicados)))
    else:
        datos.append(("Filtros aplicados", "sin filtros"))
    if reporte.avisos:
        datos.append(("Avisos", " · ".join(reporte.avisos)))
    return datos


def sanear_nombre(texto: str) -> str:
    """El título del reporte convertido en nombre de archivo seguro."""
    return sanear_nombre_archivo(texto, respaldo="reporte")
