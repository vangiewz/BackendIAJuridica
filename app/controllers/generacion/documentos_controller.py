"""HU-14 y HU-15: generar borradores y versionarlos sin destruir lo anterior."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.generacion.documento_generado import DocumentoGenerado
from app.models.generacion.esquemas import (
    CampoPlantilla, DocumentoGeneradoResponse, InterpretacionResponse, PlantillaResponse,
    VersionResumen,
)
from app.models.ia.esquemas import BorradorIA
from app.services.generacion import exportadores, plantillas
from app.services.ia.generacion import generar_borrador
from app.services.ia.interpretacion_documento import interpretar


class GeneracionNoDisponibleError(Exception):
    """La IA local no pudo producir un borrador verificable."""


class DocumentoGeneradoNoEncontradoError(Exception):
    pass


class TipoFueraDeAlcanceError(Exception):
    pass


def interpretar_pedido(texto: str, tipo=None, datos: dict | None = None,
                       client=None) -> InterpretacionResponse:
    """Traduce una frase del usuario a los datos de la plantilla, sin generar nada.

    Es un paso previo y barato: no redacta el documento ni lo guarda, solo deja el
    formulario listo para que el usuario lo revise. Por eso no toca el versionado.
    """
    if not get_settings().ia_enabled:
        raise GeneracionNoDisponibleError("La función de IA está desactivada.")
    return interpretar(texto, tipo, datos, client)


def listar_plantillas() -> list[PlantillaResponse]:
    return [PlantillaResponse(tipo_documento=p.tipo, titulo=p.titulo,
                campos=[CampoPlantilla(clave=c.clave, etiqueta=c.etiqueta,
                                       obligatorio=c.obligatorio) for c in p.campos],
                clausulas=list(p.clausulas))
            for p in plantillas.PLANTILLAS.values()]


def _respuesta(fila: DocumentoGenerado, borrador: BorradorIA | None = None):
    return DocumentoGeneradoResponse(
        id=fila.id, tipo_documento=fila.tipo_documento, contenido=fila.contenido,
        version=fila.version, documento_padre_id=fila.documento_padre_id,
        campos_faltantes=plantillas.faltantes_en_contenido(fila.contenido),
        fuentes=borrador.fuentes if borrador else [],
        ia_error=borrador.motivo if borrador else None, creado_en=fila.creado_en)


def _guardar(db: Session, usuario_id: UUID, tipo, contenido: str,
             padre: DocumentoGenerado | None = None) -> DocumentoGenerado:
    fila = DocumentoGenerado(usuario_id=usuario_id, tipo_documento=tipo, contenido=contenido,
                             version=(padre.version + 1) if padre else 1,
                             documento_padre_id=padre.id if padre else None)
    db.add(fila)
    db.commit()
    db.refresh(fila)
    return fila


def generar(db: Session, usuario_id: UUID, tipo, datos: dict) -> DocumentoGeneradoResponse:
    try:
        plantillas.obtener(tipo)
    except ValueError as exc:
        raise TipoFueraDeAlcanceError(str(exc)) from None
    if not get_settings().ia_enabled:
        raise GeneracionNoDisponibleError("La función de IA está desactivada.")
    borrador = generar_borrador(db, tipo, datos)
    if not borrador.disponible:
        raise GeneracionNoDisponibleError(borrador.motivo)
    return _respuesta(_guardar(db, usuario_id, tipo, borrador.contenido), borrador)


def exportar(db: Session, documento_id: UUID, usuario_id: UUID,
             formato: str) -> tuple[bytes, str, str]:
    """Devuelve (contenido, nombre de archivo, tipo MIME) del borrador ya guardado.

    Se apoya en `obtener`, que solo encuentra documentos del usuario del token: un id
    ajeno da 404 igual que en el resto del módulo. No vuelve a llamar al modelo, así que
    el archivo dice exactamente lo mismo que la versión guardada.
    """
    documento = obtener(db, documento_id, usuario_id)
    return (exportadores.generar(documento, formato),
            exportadores.nombre_de_archivo(documento, formato),
            exportadores.TIPOS_MIME[formato])


def _obtener(db: Session, documento_id: UUID, usuario_id: UUID) -> DocumentoGenerado:
    fila = db.scalar(select(DocumentoGenerado).where(
        DocumentoGenerado.id == documento_id, DocumentoGenerado.usuario_id == usuario_id))
    if not fila:
        raise DocumentoGeneradoNoEncontradoError("Documento generado no encontrado")
    return fila


def obtener(db: Session, documento_id: UUID, usuario_id: UUID) -> DocumentoGeneradoResponse:
    return _respuesta(_obtener(db, documento_id, usuario_id))


def listar(db: Session, usuario_id: UUID, limite: int = 50) -> list[DocumentoGeneradoResponse]:
    filas = db.scalars(select(DocumentoGenerado)
        .where(DocumentoGenerado.usuario_id == usuario_id)
        .order_by(DocumentoGenerado.creado_en.desc()).limit(limite)).all()
    return [_respuesta(f) for f in filas]


def _raiz(db: Session, fila: DocumentoGenerado) -> DocumentoGenerado:
    visitados = set()
    while fila.documento_padre_id and fila.documento_padre_id not in visitados:
        visitados.add(fila.id)
        padre = db.get(DocumentoGenerado, fila.documento_padre_id)
        if not padre:
            break
        fila = padre
    return fila


def versiones(db: Session, documento_id: UUID, usuario_id: UUID) -> list[VersionResumen]:
    """Devuelve la cadena completa: ninguna revisión reemplaza a la anterior."""
    actual = _obtener(db, documento_id, usuario_id)
    raiz = _raiz(db, actual)
    cadena = [raiz]
    pendientes = [raiz.id]
    while pendientes:
        hijos = db.scalars(select(DocumentoGenerado).where(
            DocumentoGenerado.documento_padre_id.in_(pendientes),
            DocumentoGenerado.usuario_id == usuario_id)).all()
        cadena.extend(hijos)
        pendientes = [h.id for h in hijos]
    cadena.sort(key=lambda f: (f.version, f.creado_en))
    return [VersionResumen(id=f.id, version=f.version,
                           documento_padre_id=f.documento_padre_id, creado_en=f.creado_en)
            for f in cadena]


def revisar(db: Session, documento_id: UUID, usuario_id: UUID, instruccion: str | None,
            datos: dict | None, contenido: str | None) -> DocumentoGeneradoResponse:
    """Crea una versión nueva. La anterior queda intacta y sigue siendo recuperable."""
    padre = _obtener(db, documento_id, usuario_id)
    if contenido:
        # Edición manual: el texto del usuario se guarda tal cual, sin pasar por el modelo.
        return _respuesta(_guardar(db, usuario_id, padre.tipo_documento, contenido, padre))
    if not instruccion and not datos:
        raise ValueError("Indique un cambio, datos corregidos o el contenido editado")
    if not get_settings().ia_enabled:
        raise GeneracionNoDisponibleError("La función de IA está desactivada.")
    plantilla = plantillas.obtener(padre.tipo_documento)
    combinados = {**plantillas.datos_desde_contenido(plantilla, padre.contenido), **(datos or {})}
    borrador = generar_borrador(db, padre.tipo_documento, combinados, instruccion, padre.contenido)
    if not borrador.disponible:
        raise GeneracionNoDisponibleError(borrador.motivo)
    return _respuesta(_guardar(db, usuario_id, padre.tipo_documento, borrador.contenido, padre),
                      borrador)
