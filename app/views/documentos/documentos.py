from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencias import usuario_actual
from app.models.auth.usuario import Usuario
from app.models.documentos.esquemas import DocumentoResponse, DocumentosResponse, DocumentoDetalle
from app.controllers.documentos.carga_controller import cargar_documento
from app.controllers.documentos.consulta_documentos_controller import obtener_documentos, obtener_documento
from app.controllers.documentos.errores import DocumentoNoEncontradoError, TamanoExcedidoError
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
