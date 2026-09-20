"""Exportadores del reporte: reciben el resultado ya calculado y devuelven bytes.

Ninguno consulta la base ni llama al modelo de lenguaje: trabajan sobre el mismo
`ReporteResultado` que se mostró en pantalla, así que el archivo y la pantalla no pueden
discrepar. Se genera todo en memoria, sin escribir archivos temporales en disco.
"""
from datetime import datetime, timezone

from app.models.reportes.esquemas import FormatoExportacion, ReporteResultado
from app.services.reportes.exportadores import comun
from app.services.reportes.fechas import ZONA_BOLIVIA

TIPOS_MIME: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def generar(reporte: ReporteResultado, formato: FormatoExportacion) -> bytes:
    if formato not in TIPOS_MIME:
        raise ValueError(f"Formato no admitido: {formato}")
    # Import perezoso: cada formato trae su librería y no hace falta cargarlas todas
    # para generar una sola.
    if formato == "xlsx":
        from app.services.reportes.exportadores import excel
        return excel.generar(reporte)
    if formato == "docx":
        from app.services.reportes.exportadores import word
        return word.generar(reporte)
    if formato == "pptx":
        from app.services.reportes.exportadores import powerpoint
        return powerpoint.generar(reporte)
    from app.services.reportes.exportadores import pdf
    return pdf.generar(reporte)


def nombre_de_archivo(reporte: ReporteResultado, formato: FormatoExportacion) -> str:
    """Nombre seguro: el título del reporte saneado, la fecha y la extensión del formato.

    El título puede venir del modelo, así que se reduce a caracteres inocuos antes de
    llegar a una cabecera HTTP. No se construye ninguna ruta con él.
    """
    dia = datetime.now(timezone.utc).astimezone(ZONA_BOLIVIA).strftime("%Y-%m-%d")
    return f"reporte_{comun.sanear_nombre(reporte.titulo)}_{dia}.{formato}"
