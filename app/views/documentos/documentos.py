from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencias import usuario_actual
from app.models.auth.usuario import Usuario
from app.models.documentos.esquemas import (
    DocumentoResponse, DocumentosResponse, DocumentoDetalle,
    ComparacionRequest, ComparacionResponse, ComparacionesResponse
)
from app.controllers.documentos.carga_controller import cargar_documento
from app.controllers.documentos.consulta_documentos_controller import obtener_documentos, obtener_documento
from app.controllers.documentos.comparacion_controller import (
    comparar_documentos, obtener_comparaciones, obtener_comparacion
)
from app.controllers.documentos.errores import (
    DocumentoNoEncontradoError, TamanoExcedidoError,
    MismoDocumentoError, DocumentoSinTextoComparableError
)
from app.services.documentos.extractor_documento import FormatoNoSoportadoError

router = APIRouter(prefix="/documentos", tags=["documentos"])

@router.post("", response_model=DocumentoResponse, status_code=status.HTTP_201_CREATED)
async def upload_documento(
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual)
):
    try:
        contenido = await archivo.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Error leyendo el archivo")
        
    try:
        # El controller espera bytes y str, no UploadFile
        return cargar_documento(db, contenido, archivo.filename or "archivo_sin_nombre", usuario.id)
    except FormatoNoSoportadoError as e:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(e))
    except TamanoExcedidoError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))


@router.get("", response_model=DocumentosResponse)
def list_documentos(
    limite: int = Query(50, ge=1, le=50),
    desplazamiento: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual)
):
    return obtener_documentos(db, usuario.id, limite, desplazamiento)


@router.post("/comparaciones", response_model=ComparacionResponse, status_code=status.HTTP_201_CREATED)
def comparar(
    request: ComparacionRequest,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual)
):
    """Compara dos documentos propios y devuelve las diferencias detectadas."""
    try:
        return comparar_documentos(db, usuario.id, request.documento_a_id, request.documento_b_id)
    except MismoDocumentoError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except DocumentoNoEncontradoError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DocumentoSinTextoComparableError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/comparaciones", response_model=ComparacionesResponse)
def listar_comparaciones(
    limite: int = Query(50, ge=1, le=50),
    desplazamiento: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual)
):
    """Historial de comparaciones del usuario."""
    return obtener_comparaciones(db, usuario.id, limite, desplazamiento)


@router.get("/comparaciones/{comparacion_id}", response_model=ComparacionResponse)
def leer_comparacion(
    comparacion_id: UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual)
):
    """Relee una comparación guardada. No vuelve a compararla."""
    try:
        return obtener_comparacion(db, comparacion_id, usuario.id)
    except DocumentoNoEncontradoError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# Esta ruta va despues de /comparaciones: declarada antes, /{id} capturaria
# "comparaciones" como si fuera un UUID.
@router.get("/{id}", response_model=DocumentoDetalle)
def get_documento(
    id: UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual)
):
    try:
        return obtener_documento(db, id, usuario.id)
    except DocumentoNoEncontradoError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
