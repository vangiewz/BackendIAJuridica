"""Esquemas del reporte dinámico.

`EspecificacionReporte` es el único formato que el modelo de lenguaje puede producir y
lo único que el backend acepta para construir una consulta. No hay ningún campo por el
que pueda viajar SQL: cada nombre se valida después contra el catálogo.

La misma especificación se devuelve al frontend para que una segunda petición
("ahora mostralo como gráfico") pueda partir de ella. Lo que vuelve del cliente se
revalida igual que lo que produce el modelo: no es una vía de confianza.
"""
from typing import Any, Literal

from pydantic import BaseModel, Field

Operador = Literal["igual", "distinto", "contiene", "mayor_que", "menor_que", "entre",
                   "desde", "hasta"]
Funcion = Literal["conteo", "suma", "promedio", "minimo", "maximo"]
Visualizacion = Literal["tabla", "barras", "torta", "resumen"]
Direccion = Literal["asc", "desc"]
# Los únicos formatos que se pueden generar. No hay forma de pedir otra extensión.
FormatoExportacion = Literal["pdf", "docx", "xlsx", "pptx"]
# En la especificación viaja como enum con "" para "sin exportación": una unión con null
# complica la gramática con la que el modelo genera el JSON y no aporta nada.
FormatoPedido = Literal["", "pdf", "docx", "xlsx", "pptx"]


class FiltroReporte(BaseModel):
    campo: str = ""
    operador: Operador = "igual"
    valor: str = ""
    # Solo lo usa "entre"; el resto lo deja vacío.
    valor_hasta: str = ""


class OrdenReporte(BaseModel):
    campo: str = ""
    direccion: Direccion = "desc"


class AgregacionReporte(BaseModel):
    funcion: Funcion = "conteo"
    # Vacío solo para "conteo", que cuenta filas.
    campo: str = ""


class EspecificacionReporte(BaseModel):
    """Qué reporte hay que construir. Entidad vacía significa que no se pudo interpretar."""
    entidad: str = ""
    titulo: str = ""
    columnas: list[str] = Field(default_factory=list)
    filtros: list[FiltroReporte] = Field(default_factory=list)
    agrupacion: list[str] = Field(default_factory=list)
    agregaciones: list[AgregacionReporte] = Field(default_factory=list)
    orden: list[OrdenReporte] = Field(default_factory=list)
    visualizacion: Visualizacion = "tabla"
    # Formato de archivo pedido dentro de la misma frase ("...y exportalo a Excel").
    # Es independiente de `visualizacion`: cómo se ve en pantalla y en qué archivo baja
    # son dos decisiones distintas.
    exportacion: FormatoPedido = ""
    # Sin restricción aquí a propósito: un límite fuera de rango se recorta al construir
    # la consulta en vez de invalidar toda la interpretación del modelo.
    limite: int = 100
    # Lo que el modelo necesita preguntar cuando la petición no alcanza para un reporte.
    aclaracion: str = ""


class ReporteRequest(BaseModel):
    peticion: str = Field(min_length=3, max_length=500)
    # Si viene, la petición se interpreta como un ajuste sobre este reporte.
    especificacion_actual: EspecificacionReporte | None = None


class EjecucionRequest(BaseModel):
    """Ejecutar una especificación armada en el constructor visual.

    No pasa por el modelo de lenguaje. Como llega del cliente, se revalida igual que
    una especificación interpretada: el catálogo y el filtro por usuario se aplican
    siempre, del mismo modo.
    """
    especificacion: EspecificacionReporte


class ExportacionRequest(BaseModel):
    """Exportar un reporte ya interpretado. No vuelve a pasar por el modelo de lenguaje.

    La especificación llega del cliente, así que se revalida entera contra el catálogo y
    la consulta se rehace con el usuario del token: una especificación manipulada no
    puede alcanzar datos de otro usuario.
    """
    especificacion: EspecificacionReporte
    formato: FormatoExportacion
    # Solo para dejar constancia en el archivo de qué se pidió; no se reinterpreta.
    peticion: str = Field(default="", max_length=500)


class ColumnaReporte(BaseModel):
    clave: str
    etiqueta: str
    tipo: str


class ReporteResultado(BaseModel):
    titulo: str
    entidad: str
    entidad_etiqueta: str
    visualizacion: Visualizacion
    columnas: list[ColumnaReporte]
    filas: list[dict[str, Any]]
    total: int
    filtros_aplicados: list[str] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    # Ruta de detalle de la entidad, cuando cada fila se puede abrir.
    ruta_detalle: str | None = None
    especificacion: EspecificacionReporte
    # Formato que el usuario pidió en la frase, si pidió alguno: la pantalla lo usa para
    # lanzar esa descarga sin dejar de mostrar el reporte.
    exportacion: FormatoPedido = ""
    # La petición original, tal cual se escribió; queda registrada en los archivos.
    peticion: str = ""
    interpretacion_ms: int = 0
    consulta_ms: int = 0
