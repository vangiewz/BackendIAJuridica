from uuid import UUID
from dataclasses import asdict
from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from app.models.documentos.documento import Documento
from app.models.documentos.comparacion import ComparacionDocumentos
from app.models.documentos.esquemas import (
    ComparacionResponse, ComparacionesResponse, DiferenciaResponse, ItemComparacion
)
from app.models.shared.enums import EstadoProceso
from app.services.documentos.comparador import comparar
from app.controllers.documentos.errores import (
    DocumentoNoEncontradoError, MismoDocumentoError, DocumentoSinTextoComparableError
)


def _obtener_documento(db: Session, documento_id: UUID, usuario_id: UUID) -> Documento:
    """El filtro por usuario_id es el control de acceso: el documento de otro no existe."""
    doc = db.scalar(
        select(Documento).where(Documento.id == documento_id, Documento.usuario_id == usuario_id)
    )
    if not doc:
        raise DocumentoNoEncontradoError(f"Documento {documento_id} no encontrado.")
    return doc


def _exigir_texto(doc: Documento) -> str:
    if doc.estado != EstadoProceso.COMPLETADO or not doc.texto_extraido:
        raise DocumentoSinTextoComparableError(
            f"El documento '{doc.nombre_archivo}' no tiene texto extraído para comparar."
        )
    return doc.texto_extraido


def comparar_documentos(
    db: Session, usuario_id: UUID, documento_a_id: UUID, documento_b_id: UUID
) -> ComparacionResponse:
    if documento_a_id == documento_b_id:
        raise MismoDocumentoError("Elegí dos documentos distintos para comparar.")

    doc_a = _obtener_documento(db, documento_a_id, usuario_id)
    doc_b = _obtener_documento(db, documento_b_id, usuario_id)

    comparacion = comparar(_exigir_texto(doc_a), _exigir_texto(doc_b))
    items = [asdict(d) for d in comparacion.diferencias]

    fila = ComparacionDocumentos(
        usuario_id=usuario_id,
        documento_a_id=doc_a.id,
        documento_b_id=doc_b.id,
        # La columna `diferencias` ya existe como JSON: guarda el resultado completo,
        # con la estrategia usada, para poder releer la comparacion tal como se mostro.
        diferencias={
            "estrategia": comparacion.estrategia,
            "cantidad_cambios": len(items),
            "items": items,
        },
    )
    db.add(fila)
    db.commit()
    db.refresh(fila)

    return ComparacionResponse(
        id=fila.id,
        documento_a_id=doc_a.id,
        documento_b_id=doc_b.id,
        nombre_a=doc_a.nombre_archivo,
        nombre_b=doc_b.nombre_archivo,
        estrategia=comparacion.estrategia,
        cantidad_cambios=len(items),
        diferencias=[DiferenciaResponse(**item) for item in items],
        creada_en=fila.creada_en,
    )


# --- Historial de comparaciones (HU-19): solo lectura, nunca recalcula ---

def _nombres_de_documentos(db: Session, filas: list[ComparacionDocumentos]) -> dict:
    """Nombre de archivo de todos los documentos citados, en una sola consulta."""
    ids = {f.documento_a_id for f in filas} | {f.documento_b_id for f in filas}
    if not ids:
        return {}
    pares = db.execute(
        select(Documento.id, Documento.nombre_archivo).where(Documento.id.in_(ids))
    ).all()
    return {id_: nombre for id_, nombre in pares}


def obtener_comparaciones(
    db: Session, usuario_id: UUID, limite: int = 50, desplazamiento: int = 0
) -> ComparacionesResponse:
    total = db.scalar(
        select(func.count()).select_from(ComparacionDocumentos)
        .where(ComparacionDocumentos.usuario_id == usuario_id)
    ) or 0

    filas = list(db.scalars(
        select(ComparacionDocumentos)
        .where(ComparacionDocumentos.usuario_id == usuario_id)
        .order_by(desc(ComparacionDocumentos.creada_en))
        .limit(limite)
        .offset(desplazamiento)
    ).all())

    nombres = _nombres_de_documentos(db, filas)

    items = [
        ItemComparacion(
            id=fila.id,
            documento_a_id=fila.documento_a_id,
            documento_b_id=fila.documento_b_id,
            # El documento pudo borrarse despues de la comparacion: el historial no
            # se rompe por eso, muestra que ya no esta disponible.
            nombre_a=nombres.get(fila.documento_a_id, "Documento no disponible"),
            nombre_b=nombres.get(fila.documento_b_id, "Documento no disponible"),
            estrategia=(fila.diferencias or {}).get("estrategia", ""),
            cantidad_cambios=(fila.diferencias or {}).get("cantidad_cambios", 0),
            creada_en=fila.creada_en,
        )
        for fila in filas
    ]

    return ComparacionesResponse(total=total, items=items)


def obtener_comparacion(db: Session, comparacion_id: UUID, usuario_id: UUID) -> ComparacionResponse:
    """Relee una comparacion guardada. No vuelve a comparar nada."""
    fila = db.scalar(
        select(ComparacionDocumentos).where(
            ComparacionDocumentos.id == comparacion_id,
            ComparacionDocumentos.usuario_id == usuario_id,
        )
    )
    if not fila:
        raise DocumentoNoEncontradoError(f"Comparación {comparacion_id} no encontrada.")

    guardado = fila.diferencias or {}
    items = guardado.get("items", [])
    nombres = _nombres_de_documentos(db, [fila])

    return ComparacionResponse(
        id=fila.id,
        documento_a_id=fila.documento_a_id,
        documento_b_id=fila.documento_b_id,
        nombre_a=nombres.get(fila.documento_a_id, "Documento no disponible"),
        nombre_b=nombres.get(fila.documento_b_id, "Documento no disponible"),
        estrategia=guardado.get("estrategia", ""),
        cantidad_cambios=guardado.get("cantidad_cambios", len(items)),
        diferencias=[DiferenciaResponse(**item) for item in items],
        creada_en=fila.creada_en,
    )
