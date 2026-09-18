from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc

from app.models.documentos.documento import Documento
from app.models.documentos.esquemas import DocumentosResponse, ItemDocumento, DocumentoDetalle
from app.controllers.documentos.errores import DocumentoNoEncontradoError

def obtener_documentos(db: Session, usuario_id: UUID, limite: int = 50, desplazamiento: int = 0) -> DocumentosResponse:
    total = db.scalar(select(func.count()).select_from(Documento).where(Documento.usuario_id == usuario_id)) or 0

    stmt = (
        select(Documento)
        .where(Documento.usuario_id == usuario_id)
        .order_by(desc(Documento.subido_en))
        .limit(limite)
        .offset(desplazamiento)
    )

    resultados = db.scalars(stmt).all()
    
    items = [
        ItemDocumento(
            id=doc.id,
            nombre_archivo=doc.nombre_archivo,
            tipo_documento=doc.tipo_documento,
            estado=doc.estado,
            subido_en=doc.subido_en
        )
        for doc in resultados
    ]

    return DocumentosResponse(total=total, items=items)

def obtener_documento(db: Session, documento_id: UUID, usuario_id: UUID) -> DocumentoDetalle:
    doc = db.scalar(select(Documento).where(Documento.id == documento_id, Documento.usuario_id == usuario_id))
    if not doc:
        raise DocumentoNoEncontradoError(f"Documento {documento_id} no encontrado.")

    return DocumentoDetalle(
        id=doc.id,
        nombre_archivo=doc.nombre_archivo,
        tipo_documento=doc.tipo_documento,
        terminos_detectados=doc.terminos_detectados or [],
        cantidad_caracteres=doc.cantidad_caracteres,
        estado=doc.estado,
        motivo_fallo=doc.motivo_fallo,
        subido_en=doc.subido_en,
        texto_extraido=doc.texto_extraido
    )
