from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Query, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencias import usuario_actual
from app.models.auth.usuario import Usuario
from app.models.consultas.esquemas import ConsultaRequest, ConsultaResponse, HistorialResponse
from app.controllers.consultas.resolver_consulta_controller import (
    documento_del_usuario, resolver_consulta,
)
from app.controllers.consultas.historial_controller import obtener_historial, obtener_consulta, consulta_por_operacion
from app.controllers.consultas.errores import ConsultaNoEncontradaError

router = APIRouter(prefix="/consultas", tags=["Consultas Juridicas"])


def _procesar(consulta_id, usuario_id, request):
    from app.core.database import obtener_engine
    from app.models.consultas.consulta import Consulta
    from app.models.shared.enums import EstadoProceso
    with Session(obtener_engine()) as db:
        try:
            consulta = db.get(Consulta, consulta_id)
            resolver_consulta(db, request, usuario_id, consulta)
        except Exception:
            db.rollback()
            consulta = db.get(Consulta, consulta_id)
            if consulta:
                consulta.estado = EstadoProceso.FALLIDO
                consulta.etapa_ia = "No se pudo completar"
                consulta.ia_error = "No se pudo completar la consulta. Puede intentarlo nuevamente."
                db.commit()


@router.post("/iniciar", status_code=status.HTTP_202_ACCEPTED)
def iniciar_consulta(request: ConsultaRequest, tareas: BackgroundTasks, response: Response,
                     db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    from app.models.consultas.consulta import Consulta
    from app.models.shared.enums import EstadoProceso

    if request.client_op_id:
        existente = consulta_por_operacion(db, usuario.id, request.client_op_id)
        if existente:
            response.status_code = status.HTTP_200_OK
            return {"id": existente.id, "estado": existente.estado}

    # El documento se valida contra el usuario del token antes de dejarlo anotado:
    # un id ajeno no queda ni siquiera registrado en la consulta.
    documento = documento_del_usuario(db, request.documento_id, usuario.id)
    consulta = Consulta(usuario_id=usuario.id, texto=request.texto, estado=EstadoProceso.PROCESANDO,
                        documento_id=documento.id if documento else None,
                        client_op_id=request.client_op_id,
                        terminos_detectados=[], etapa_ia="Preparando consulta...")
    try:
        db.add(consulta)
        db.commit()
        db.refresh(consulta)
    except IntegrityError:
        # Otra peticion con el mismo client_op_id gano la carrera entre el SELECT de
        # arriba y este commit. La constraint la freno antes de duplicar nada: se
        # devuelve la que quedo, que es la misma respuesta que habria dado el SELECT.
        db.rollback()
        gemela = consulta_por_operacion(db, usuario.id, request.client_op_id)
        if gemela is None:
            raise
        response.status_code = status.HTTP_200_OK
        return {"id": gemela.id, "estado": gemela.estado}
    tareas.add_task(_procesar, consulta.id, usuario.id, request)
    return {"id": consulta.id, "estado": consulta.estado}

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
