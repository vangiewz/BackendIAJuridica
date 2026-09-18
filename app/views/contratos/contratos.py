from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencias import usuario_actual
from app.models.auth.usuario import Usuario
from app.models.contratos.esquemas import AnalisisResponse
from app.controllers.documentos.errores import DocumentoNoEncontradoError
from app.controllers.contratos.errores import DocumentoNoAnalizableError
from app.controllers.contratos.analisis_controller import analizar_documento, obtener_analisis

router = APIRouter(prefix="/documentos", tags=["contratos"])

@router.post("/{id}/analisis", response_model=AnalisisResponse, status_code=status.HTTP_201_CREATED)
def analizar_contrato(
    id: UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual)
):
    try:
        return analizar_documento(db, id, usuario.id)
    except DocumentoNoEncontradoError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DocumentoNoAnalizableError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

@router.get("/{id}/analisis", response_model=AnalisisResponse)
def get_analisis_contrato(
    id: UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual)
):
    try:
        return obtener_analisis(db, id, usuario.id)
    except DocumentoNoEncontradoError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
