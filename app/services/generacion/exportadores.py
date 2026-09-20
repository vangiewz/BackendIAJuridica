"""HU-14: el borrador generado, en Word y en PDF.

El archivo no reinterpreta nada: parte del contenido que ya está guardado, el mismo que
se ve en pantalla. No interviene el modelo de lenguaje, así que exportar dos veces la
misma versión da dos veces el mismo documento.

Lo único que agrega el exportador es forma: los títulos y las cláusulas se ven como
títulos y cláusulas, y **los datos pendientes se resaltan en rojo** en vez de pasar
desapercibidos. Un borrador incompleto no puede parecer un documento terminado.
"""
import re
from datetime import datetime, timezone
from io import BytesIO
from xml.sax.saxutils import escape

from app.models.generacion.esquemas import DocumentoGeneradoResponse
from app.services.reportes.fechas import ZONA_BOLIVIA
from app.services.shared.normalizacion import sanear_nombre_archivo

TIPOS_MIME = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}

AVISO = ("Borrador de apoyo generado con asistencia de inteligencia artificial sobre "
         "normativa civil boliviana. No sustituye el criterio profesional: debe revisarlo "
         "un abogado antes de firmarlo o presentarlo.")

# Así arma el documento `generacion._ensamblar`: un título, un bloque de datos, las
# cláusulas con su ordinal y el cierre con las firmas.
RE_CLAUSULA = re.compile(r"^([A-ZÁÉÍÓÚÑ]+(?:\s+\d+)?)\.-\s+(.+)$")
RE_FIRMA = re.compile(r"^_{3,}")
RE_PENDIENTE = re.compile(r"(\[FALTA:\s*[^\]]+\])")

TITULO, SECCION, CLAUSULA, DATO, FIRMA, PARRAFO = (
    "titulo", "seccion", "clausula", "dato", "firma", "parrafo")


def _clasificar(linea: str, indice: int) -> str:
    if indice == 0:
        return TITULO
    if RE_FIRMA.match(linea):
        return FIRMA
    if RE_CLAUSULA.match(linea):
        return CLAUSULA
    sin_marcadores = RE_PENDIENTE.sub("", linea)
    if ": " in sin_marcadores:
        return DATO
    # Una línea corta y toda en mayúsculas es un encabezado de sección.
    letras = [c for c in sin_marcadores if c.isalpha()]
    if letras and len(linea) < 60 and all(c.isupper() for c in letras):
        return SECCION
    return PARRAFO


def bloques(contenido: str) -> list[tuple[str, str]]:
    """El borrador partido en (tipo de línea, texto), sin las líneas vacías."""
    salida = []
    for linea in (contenido or "").splitlines():
        limpia = linea.rstrip()
        if not limpia.strip():
            continue
        salida.append((_clasificar(limpia.strip(), len(salida)), limpia.strip()))
    return salida


def _partes_con_pendientes(texto: str) -> list[tuple[str, bool]]:
    """(fragmento, es_pendiente) para poder resaltar solo los marcadores."""
    return [(parte, bool(parte.startswith("[FALTA:")))
            for parte in RE_PENDIENTE.split(texto) if parte]


def _generado_en() -> str:
    return datetime.now(timezone.utc).astimezone(ZONA_BOLIVIA).strftime("%d/%m/%Y %H:%M")


def _ficha(documento: DocumentoGeneradoResponse) -> list[str]:
    lineas = [f"Tipo: {documento.tipo_documento.value}",
              f"Versión: {documento.version}",
              f"Generado el {_generado_en()}"]
    if documento.campos_faltantes:
        lineas.append("Datos pendientes de completar: "
                      + ", ".join(documento.campos_faltantes))
    return lineas


# --- Word ------------------------------------------------------------------------

def _a_word(documento: DocumentoGeneradoResponse) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor

    ROJO = RGBColor(0xC8, 0x10, 0x2E)
    SUAVE = RGBColor(0x5F, 0x59, 0x52)
    archivo = Document()

    def escribir(parrafo, texto, negrita=False):
        for fragmento, pendiente in _partes_con_pendientes(texto):
            corrida = parrafo.add_run(fragmento)
            corrida.bold = negrita or pendiente
            if pendiente:
                corrida.font.color.rgb = ROJO

    for tipo, texto in bloques(documento.contenido):
        if tipo == TITULO:
            titulo = archivo.add_heading(level=1)
            titulo.alignment = WD_ALIGN_PARAGRAPH.CENTER
            escribir(titulo, texto)
            continue
        if tipo in (SECCION, CLAUSULA):
            escribir(archivo.add_heading(level=2), texto)
            continue
        parrafo = archivo.add_paragraph()
        escribir(parrafo, texto)
        parrafo.paragraph_format.space_after = Pt(4 if tipo in (DATO, FIRMA) else 8)
        if tipo == PARRAFO:
            parrafo.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    archivo.add_page_break()
    archivo.add_heading("Datos de este borrador", level=2)
    for linea in _ficha(documento):
        archivo.add_paragraph(linea)
    nota = archivo.add_paragraph()
    corrida = nota.add_run(AVISO)
    corrida.italic = True
    corrida.font.size = Pt(9)
    corrida.font.color.rgb = SUAVE

    memoria = BytesIO()
    archivo.save(memoria)
    return memoria.getvalue()


# --- PDF -------------------------------------------------------------------------

def _marcado(texto: str) -> str:
    """El texto para ReportLab, con los pendientes en rojo y lo demás escapado."""
    return "".join(
        f'<font color="#C8102E"><b>{escape(fragmento)}</b></font>' if pendiente
        else escape(fragmento)
        for fragmento, pendiente in _partes_con_pendientes(texto))


def _a_pdf(documento: DocumentoGeneradoResponse) -> bytes:
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    base = getSampleStyleSheet()
    estilos = {
        TITULO: ParagraphStyle("t", parent=base["Title"], fontSize=15, alignment=TA_CENTER,
                               spaceAfter=12),
        SECCION: ParagraphStyle("s", parent=base["Heading2"], fontSize=11, spaceBefore=10,
                                spaceAfter=4),
        CLAUSULA: ParagraphStyle("c", parent=base["Heading2"], fontSize=11, spaceBefore=10,
                                 spaceAfter=4),
        DATO: ParagraphStyle("d", parent=base["BodyText"], fontSize=10, leading=14,
                             spaceAfter=2),
        PARRAFO: ParagraphStyle("p", parent=base["BodyText"], fontSize=10, leading=15,
                                alignment=TA_JUSTIFY, spaceAfter=6),
        FIRMA: ParagraphStyle("f", parent=base["BodyText"], fontSize=10, leading=14,
                              spaceAfter=2),
    }
    ficha = ParagraphStyle("ficha", parent=base["BodyText"], fontSize=9, leading=12,
                           textColor="#5F5952")

    piezas = [Paragraph(_marcado(texto), estilos[tipo])
              for tipo, texto in bloques(documento.contenido)]
    piezas.append(Spacer(1, 16))
    for linea in _ficha(documento):
        piezas.append(Paragraph(escape(linea), ficha))
    piezas.append(Spacer(1, 6))
    piezas.append(Paragraph(f"<i>{escape(AVISO)}</i>", ficha))

    memoria = BytesIO()
    SimpleDocTemplate(
        memoria, pagesize=A4, title=f"Borrador {documento.tipo_documento.value}",
        author="Asistencia Jurídica Civil", leftMargin=22 * mm, rightMargin=22 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm).build(piezas)
    return memoria.getvalue()


# --- Entrada ---------------------------------------------------------------------

def generar(documento: DocumentoGeneradoResponse, formato: str) -> bytes:
    if formato == "docx":
        return _a_word(documento)
    if formato == "pdf":
        return _a_pdf(documento)
    raise ValueError(f"Formato no admitido: {formato}")


def nombre_de_archivo(documento: DocumentoGeneradoResponse, formato: str) -> str:
    dia = datetime.now(timezone.utc).astimezone(ZONA_BOLIVIA).strftime("%Y-%m-%d")
    tipo = sanear_nombre_archivo(documento.tipo_documento.value, respaldo="documento")
    return f"borrador_{tipo}_v{documento.version}_{dia}.{formato}"
