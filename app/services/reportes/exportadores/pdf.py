"""PDF con ReportLab: se arma localmente, sin navegador ni servicio externo."""
from io import BytesIO

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from app.models.reportes.esquemas import ReporteResultado
from app.services.reportes.exportadores import comun

VERDE = colors.HexColor("#1B6B4A")
LINEA = colors.HexColor("#E5DFD4")
PAPEL = colors.HexColor("#FFFDF8")
PALETA = [colors.HexColor(c) for c in
          ("#1B6B4A", "#2B4C8C", "#E8A33D", "#C25A1C", "#6B3A7A", "#2F6B4F", "#C8102E")]

# A partir de cinco columnas la vertical queda apretada y el texto se parte en exceso.
COLUMNAS_PARA_APAISADO = 5


def _estilos():
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle("titulo", parent=base["Title"], fontSize=17,
                                 alignment=TA_LEFT, textColor=colors.HexColor("#22201C"),
                                 spaceAfter=4),
        "seccion": ParagraphStyle("seccion", parent=base["Heading2"], fontSize=12,
                                  textColor=VERDE, spaceBefore=10, spaceAfter=4),
        "cuerpo": ParagraphStyle("cuerpo", parent=base["BodyText"], fontSize=9, leading=12),
        "celda": ParagraphStyle("celda", parent=base["BodyText"], fontSize=8, leading=10),
        "cabecera": ParagraphStyle("cabecera", parent=base["BodyText"], fontSize=8,
                                   leading=10, textColor=colors.white, fontName="Helvetica-Bold"),
    }


def _tabla(reporte: ReporteResultado, estilos, ancho_util: float) -> Table:
    cabeceras = [Paragraph(texto, estilos["cabecera"]) for texto in comun.encabezados(reporte)]
    filas = [[Paragraph(texto, estilos["celda"]) for texto in fila]
             for fila in comun.filas_de_texto(reporte)]
    ancho = ancho_util / max(len(cabeceras), 1)
    tabla = Table([cabeceras] + filas, colWidths=[ancho] * len(cabeceras),
                  repeatRows=1)  # la cabecera se repite en cada página
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), VERDE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, LINEA),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PAPEL]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return tabla


def _grafico(reporte: ReporteResultado, ancho_util: float):
    """Gráfico vectorial dibujado con los valores reales del reporte."""
    ejes = comun.datos_de_grafico(reporte)
    if ejes is None:
        return None
    etiquetas, valores, titulo_valor = ejes
    dibujo = Drawing(ancho_util, 200)

    if reporte.visualizacion == "torta":
        torta = Pie()
        torta.x, torta.y = 40, 10
        torta.width = torta.height = 170
        torta.data = valores
        total = sum(valores) or 1
        torta.labels = [f"{e} ({v / total * 100:.0f}%)" for e, v in zip(etiquetas, valores)]
        torta.sideLabels = True
        torta.slices.strokeWidth = 0.5
        for indice in range(len(valores)):
            torta.slices[indice].fillColor = PALETA[indice % len(PALETA)]
        dibujo.add(torta)
        return dibujo

    barras = VerticalBarChart()
    barras.x, barras.y = 40, 40
    barras.width, barras.height = ancho_util - 70, 140
    barras.data = [valores]
    barras.categoryAxis.categoryNames = etiquetas
    barras.categoryAxis.labels.angle = 20
    barras.categoryAxis.labels.dy = -8
    barras.categoryAxis.labels.boxAnchor = "ne"
    barras.valueAxis.valueMin = 0
    barras.valueAxis.valueMax = max(valores) * 1.15 if max(valores) else 1
    barras.barLabels.nudge = 8
    barras.barLabelFormat = "%g"
    barras.barLabels.fontSize = 7
    for indice in range(len(valores)):
        barras.bars[(0, indice)].fillColor = PALETA[indice % len(PALETA)]
    dibujo.add(barras)
    dibujo.add(String(0, 188, titulo_valor, fontSize=8, fillColor=colors.HexColor("#5F5952")))
    return dibujo


def generar(reporte: ReporteResultado) -> bytes:
    estilos = _estilos()
    apaisado = len(reporte.columnas) >= COLUMNAS_PARA_APAISADO
    tamano = landscape(A4) if apaisado else A4
    memoria = BytesIO()
    documento = SimpleDocTemplate(memoria, pagesize=tamano, title=reporte.titulo,
                                  author="Asistencia Jurídica Civil",
                                  leftMargin=15 * mm, rightMargin=15 * mm,
                                  topMargin=15 * mm, bottomMargin=15 * mm)
    ancho_util = tamano[0] - 30 * mm

    piezas = [Paragraph(reporte.titulo, estilos["titulo"]),
              Paragraph(f"Generado el {comun.generado_en()}", estilos["cuerpo"]),
              Spacer(1, 8),
              Paragraph("Datos del reporte", estilos["seccion"])]
    for clave, valor in comun.metadatos(reporte):
        piezas.append(Paragraph(f"<b>{clave}:</b> {valor}", estilos["cuerpo"]))

    piezas.append(Paragraph("Resultados", estilos["seccion"]))
    if reporte.total == 0:
        piezas.append(Paragraph("No hay datos que cumplan esas condiciones.",
                                estilos["cuerpo"]))
    else:
        if reporte.visualizacion in ("barras", "torta"):
            dibujo = _grafico(reporte, ancho_util)
            if dibujo is not None:
                piezas.append(KeepTogether([dibujo, Spacer(1, 10)]))
        piezas.append(_tabla(reporte, estilos, ancho_util))

    documento.build(piezas)
    return memoria.getvalue()
