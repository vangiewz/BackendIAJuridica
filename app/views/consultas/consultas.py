from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencias import usuario_actual
from app.models.auth.usuario import Usuario
from app.models.consultas.esquemas import ConsultaRequest, ConsultaResponse, HistorialResponse
from app.controllers.consultas.resolver_consulta_controller import resolver_consulta
from app.controllers.consultas.historial_controller import obtener_historial, obtener_consulta
from app.controllers.consultas.errores import ConsultaNoEncontradaError

router = APIRouter(prefix="/consultas", tags=["Consultas Juridicas"])

@router.post("", response_model=ConsultaResponse, status_code=status.HTTP_201_CREATED)
def crear_consulta(
    request: ConsultaRequest,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual)
):
    return resolver_consulta(db=db, request=request, usuario_id=usuario.id)

@router.get("/historial", response_model=HistorialResponse)
def listar_historial(
    limite: int = Query(50, ge=1, le=50),
    desplazamiento: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual)
):
    return obtener_historial(db=db, usuario_id=usuario.id, limite=limite, desplazamiento=desplazamiento)

@router.get("/{id}", response_model=ConsultaResponse)
def leer_consulta(
    id: UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual)
):
    try:
        return obtener_consulta(db=db, consulta_id=id, usuario_id=usuario.id)
    except ConsultaNoEncontradaError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consulta no encontrada")
