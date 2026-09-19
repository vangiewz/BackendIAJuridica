import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conocimiento.norma import Norma
from app.models.shared.enums import EstadoVigencia
from app.services.conocimiento.perfiles_fuente import PerfilFuente
from app.services.conocimiento.parser_articulos import parsear, ArticuloParseado
from app.services.conocimiento.extractor_pdf import extraer_texto
from app.services.conocimiento.mapeo_areas import area_de
from app.controllers.conocimiento.errores import (
    CorpusIncompletoError, FuenteNoEncontradaError, FuenteNoProcesableError
)

# Donde vive el corpus que viene con el repositorio.
RUTA_DATOS = Path("data/normativa")

@dataclass(frozen=True)
class ReporteIngesta:
    codigo: str
    total_parseados: int
    insertadas: int
    actualizadas: int
    sin_cambios: int
    por_libro: dict[str, int]
    por_area: dict[str, int]

def _crear_norma(art: ArticuloParseado, perfil: PerfilFuente, descargada_en: datetime, version: int, area) -> Norma:
    return Norma(
        codigo=perfil.codigo, articulo=art.articulo, numero_articulo=art.numero,
        epigrafe=art.epigrafe, texto=art.texto, libro=art.libro,
        parte=art.parte, titulo=art.titulo, capitulo=art.capitulo, seccion=art.seccion,
        area_juridica=area, fuente_nombre=perfil.fuente_nombre,
        fuente_url=perfil.fuente_url, descargada_en=descargada_en,
        estado_vigencia=EstadoVigencia.SIN_VERIFICAR,
        version=version, vigente_desde=descargada_en, activa=True
    )

def _resolver_normas_activas(db: Session, codigo: str) -> dict[int, Norma]:
    stmt = select(Norma).where(Norma.codigo == codigo, Norma.activa == True)
    return {n.numero_articulo: n for n in db.execute(stmt).scalars()}

def _procesar_articulo(art: ArticuloParseado, perfil: PerfilFuente, descargada_en: datetime, ahora: datetime, normas_activas: dict[int, Norma], area, nuevas_normas: list[Norma], stats: dict):
    if art.numero in normas_activas:
        existente = normas_activas[art.numero]
        if existente.texto == art.texto and existente.epigrafe == art.epigrafe:
            stats["sin"] += 1
            return
        existente.activa = False
        existente.vigente_hasta = ahora
        nuevas_normas.append(_crear_norma(art, perfil, descargada_en, existente.version + 1, area))
        stats["act"] += 1
    else:
        nuevas_normas.append(_crear_norma(art, perfil, descargada_en, 1, area))
        stats["ins"] += 1

def ingerir_articulos(
    db: Session, articulos: list[ArticuloParseado], perfil: PerfilFuente, descargada_en: datetime
) -> ReporteIngesta:
    """Sincroniza articulos ya parseados con la base. Es el corazon y se prueba sin archivos."""
    if len(articulos) != perfil.total_esperado:
        raise CorpusIncompletoError(f"El parseo devolvio {len(articulos)} articulos, pero se esperaban {perfil.total_esperado}.")

    normas_activas = _resolver_normas_activas(db, perfil.codigo)
    stats = {"ins": 0, "act": 0, "sin": 0}
    por_libro = defaultdict(int)
    por_area = defaultdict(int)
    nuevas_normas = []
    ahora = datetime.now(timezone.utc)

    for art in articulos:
        por_libro[art.libro if art.libro else "sin_libro"] += 1
        area = area_de(art.numero)
        por_area[area.value if area else "sin_area"] += 1
        _procesar_articulo(art, perfil, descargada_en, ahora, normas_activas, area, nuevas_normas, stats)

    if nuevas_normas:
        db.add_all(nuevas_normas)
    try:
        db.flush()
    except Exception as e:
        db.rollback()
        raise e

    return ReporteIngesta(
        codigo=perfil.codigo, total_parseados=len(articulos),
        insertadas=stats["ins"], actualizadas=stats["act"], sin_cambios=stats["sin"],
        por_libro=dict(por_libro), por_area=dict(por_area)
    )

def ingerir_fuente(db: Session, perfil: PerfilFuente, ruta_datos: Path) -> ReporteIngesta:
    """Lee el archivo de la fuente, lo parsea y delega en ingerir_articulos."""
    ruta_archivo = ruta_datos / perfil.archivo
    if not ruta_archivo.exists():
        raise FuenteNoEncontradaError(f"El archivo {ruta_archivo} no existe.")

    texto_bruto = extraer_texto(ruta_archivo, perfil.ruido)
    articulos = parsear(texto_bruto, perfil)

    descargada_en = datetime.fromtimestamp(ruta_archivo.stat().st_mtime, tz=timezone.utc)

    return ingerir_articulos(db, articulos, perfil, descargada_en)


def _texto_del_pdf_subido(perfil: PerfilFuente, contenido: bytes) -> str:
    """
    Texto del PDF que subio el administrador.

    El archivo vive solo mientras se lo lee: la fuente de verdad del sistema es la
    tabla `normas`, no el PDF, asi que no se guarda nada en disco.
    """
    with tempfile.TemporaryDirectory() as directorio:
        ruta = Path(directorio) / Path(perfil.archivo).name
        ruta.write_bytes(contenido)
        try:
            return extraer_texto(ruta, perfil.ruido)
        except Exception as e:
            raise FuenteNoProcesableError(
                "El archivo no se pudo leer como PDF. Verificá que sea el documento original."
            ) from e


def ingerir_contenido(
    db: Session, perfil: PerfilFuente, contenido: bytes, descargada_en: datetime
) -> ReporteIngesta:
    """Misma tuberia que ingerir_fuente, pero a partir de un PDF subido."""
    texto_bruto = _texto_del_pdf_subido(perfil, contenido)
    if not texto_bruto.strip():
        raise FuenteNoProcesableError(
            "El PDF no tiene capa de texto. Suele pasar con documentos escaneados: "
            "subí el archivo original."
        )

    articulos = parsear(texto_bruto, perfil)
    return ingerir_articulos(db, articulos, perfil, descargada_en)
