from uuid import UUID
from pathlib import Path
from sqlalchemy.orm import Session
from app.models.documentos.documento import Documento
from app.models.documentos.esquemas import DocumentoResponse
from app.models.shared.enums import EstadoProceso
from app.services.documentos.extractor_documento import (
    extraer_texto, EXTENSIONES, DocumentoSinTextoError, FormatoNoSoportadoError
)
from app.services.documentos.clasificador_documental import clasificar_documento
from app.services.documentos.diccionario_tipos import VERSION_DICCIONARIO_TIPOS
from app.controllers.documentos.errores import TamanoExcedidoError

TAMANO_MAXIMO = 10 * 1024 * 1024

def cargar_documento(db: Session, contenido: bytes, nombre_archivo: str, usuario_id: UUID) -> DocumentoResponse:
    """
    Sube un documento, extrae el texto y lo clasifica.
    No se guarda el archivo original. Consecuencia que hay que asumir: no se puede volver a
    extraer con un parser mejor sin que el usuario resuba el archivo.
    """
    ext = Path(nombre_archivo).suffix.lower()
    if ext not in EXTENSIONES:
        raise FormatoNoSoportadoError(f"Extension {ext} no soportada.")

    if len(contenido) > TAMANO_MAXIMO:
        raise TamanoExcedidoError(f"El archivo supera el tamaño máximo de {TAMANO_MAXIMO} bytes.")

    doc = Documento(
        usuario_id=usuario_id,
        nombre_archivo=nombre_archivo,
        estado=EstadoProceso.PROCESANDO,
    )
    db.add(doc)
    db.flush()

    try:
        texto = extraer_texto(contenido, nombre_archivo)
        clasificacion = clasificar_documento(texto)
        
        doc.texto_extraido = texto
        doc.tipo_documento = clasificacion.tipo
        doc.terminos_detectados = list(clasificacion.terminos_detectados)
        doc.version_diccionario = VERSION_DICCIONARIO_TIPOS
        doc.cantidad_caracteres = len(texto)
        doc.estado = EstadoProceso.COMPLETADO
    except DocumentoSinTextoError:
        # El motivo lo lee el usuario, asi que dice que hacer y no solo que fallo.
        doc.estado = EstadoProceso.FALLIDO
        doc.motivo_fallo = (
            "No se pudo leer texto del archivo. Suele pasar con documentos escaneados o "
            "fotografiados, donde las paginas son imagenes y no texto. Proba subir el archivo "
            "original en PDF, DOCX o TXT."
        )
    
    db.commit()
    db.refresh(doc)

    return DocumentoResponse(
        id=doc.id,
        nombre_archivo=doc.nombre_archivo,
        tipo_documento=doc.tipo_documento,
        terminos_detectados=doc.terminos_detectados or [],
        cantidad_caracteres=doc.cantidad_caracteres,
        estado=doc.estado,
        motivo_fallo=doc.motivo_fallo,
        subido_en=doc.subido_en
    )
