"""HU-14 y HU-15: generar borradores y versionarlos sin destruir lo anterior."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.generacion.documento_generado import DocumentoGenerado
from app.models.generacion.esquemas import (
    CampoPlantilla, DocumentoGeneradoResponse, InterpretacionResponse, PlantillaResponse,
    ProblemaCampo, VersionResumen,
)
from app.models.ia.esquemas import BorradorIA
from app.services.generacion import exportadores, plantillas, revision_datos
from app.services.ia.generacion import generar_borrador
from app.services.ia.interpretacion_documento import interpretar


class GeneracionNoDisponibleError(Exception):
    """La IA local no pudo producir un borrador verificable."""


class DatosInvalidosError(Exception):
    """Hay campos que sin duda no sirven: se dice cuáles y cómo escribirlos, sin gastar una llamada a la IA."""

    def __init__(self, mensaje: str, campos: list[ProblemaCampo]):
        super().__init__(mensaje)
        self.campos = campos


class BorradorNoValidadoError(DatosInvalidosError):
    """La IA respondió, pero su borrador no pasó las reglas de seguridad (no inventar datos)."""


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
    respuesta = interpretar(texto, tipo, datos, client)
    if respuesta.tipo_documento:
        plantilla = plantillas.obtener(respuesta.tipo_documento)
        respuesta.problemas = _problemas(revision_datos.revisar_datos(plantilla, respuesta.datos))
    return respuesta


def listar_plantillas() -> list[PlantillaResponse]:
    return [PlantillaResponse(tipo_documento=p.tipo, titulo=p.titulo,
                campos=[CampoPlantilla(clave=c.clave, etiqueta=c.etiqueta,
                                       obligatorio=c.obligatorio, ejemplo=c.ejemplo) for c in p.campos],
                clausulas=list(p.clausulas))
            for p in plantillas.PLANTILLAS.values()]


def _problemas(lista) -> list[ProblemaCampo]:
    return [ProblemaCampo(clave=p.clave, etiqueta=p.etiqueta, mensaje=p.mensaje, ejemplo=p.ejemplo,
                          nivel=p.nivel) for p in lista]


def _exigir_datos_utiles(plantilla, datos: dict) -> None:
    """Antes de gastar minutos de IA: si hay campos que sin duda no sirven, se dicen ya."""
    malos = revision_datos.errores(revision_datos.revisar_datos(plantilla, datos))
    if malos:
        nombres = ", ".join(f"«{p.etiqueta}»" for p in malos)
        raise DatosInvalidosError(
            f"Corregí {'este campo' if len(malos) == 1 else 'estos campos'} antes de generar: {nombres}.",
            _problemas(malos))


def _mensaje_de_rechazo(borrador: BorradorIA) -> str:
    """Qué pasó cuando la IA respondió pero su borrador no se pudo validar, en palabras del usuario."""
    donde = f" en la cláusula «{borrador.clausula_rechazada}»" if borrador.clausula_rechazada else ""
    if borrador.motivo_codigo == "dato_no_proporcionado" and borrador.detalle_rechazo:
        return (f"La IA escribió{donde} algo que no está en tus datos ({borrador.detalle_rechazo}) "
                "y por eso no se generó el borrador: el sistema no permite inventar información. "
                "Probá de nuevo; si se repite, revisá los campos marcados o escribilos más completos.")
    if borrador.motivo_codigo == "cifra_fuera_de_fuentes" and borrador.detalle_rechazo:
        return (f"La IA escribió{donde} una cifra que no está en tus datos ({borrador.detalle_rechazo}) "
                "y por eso no se generó el borrador. Revisá que los montos, plazos e intereses estén "
                "escritos completos, con números, y probá de nuevo.")
    if borrador.motivo_codigo == "campo_inexistente":
        return ("La IA inventó un dato pendiente que el formulario no tiene y por eso no se generó el "
                "borrador. Probá de nuevo.")
    return ("La IA no logró redactar un borrador que cumpla las reglas de seguridad (no inventar datos) y "
            "por eso no se generó. Probá de nuevo; si se repite, revisá que los campos estén completos.")


def _fallar(borrador: BorradorIA, plantilla, datos: dict) -> None:
    """Convierte un borrador no disponible en el error que corresponde."""
    if not borrador.motivo_codigo:
        raise GeneracionNoDisponibleError(borrador.motivo)
    # Los campos dudosos (avisos) son los que hay que mirar primero.
    dudosos = revision_datos.revisar_datos(plantilla, datos)
    raise BorradorNoValidadoError(_mensaje_de_rechazo(borrador), _problemas(dudosos))


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
    plantilla = plantillas.obtener(tipo)
    _exigir_datos_utiles(plantilla, datos)
    borrador = generar_borrador(db, tipo, datos)
    if not borrador.disponible:
        _fallar(borrador, plantilla, datos)
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
        _fallar(borrador, plantilla, combinados)
    return _respuesta(_guardar(db, usuario_id, padre.tipo_documento, borrador.contenido, padre),
                      borrador)
