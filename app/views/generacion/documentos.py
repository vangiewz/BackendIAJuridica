from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencias import usuario_actual
from app.models.auth.usuario import Usuario
from app.models.generacion.esquemas import (
    DocumentoGeneradoResponse, FormatoBorrador, GeneracionRequest, InterpretacionRequest,
    InterpretacionResponse, PlantillaResponse, RevisionRequest, VersionResumen,
)
from app.controllers.generacion.documentos_controller import (
    DocumentoGeneradoNoEncontradoError, GeneracionNoDisponibleError, TipoFueraDeAlcanceError,
    exportar, generar, interpretar_pedido, listar, listar_plantillas, obtener, revisar,
    versiones,
)
from app.services.ia.interpretacion_documento import InterpretacionNoDisponibleError

router = APIRouter(prefix="/documentos-generados", tags=["generacion"])


@router.get("/plantillas", response_model=list[PlantillaResponse])
def endpoint_plantillas(usuario: Usuario = Depends(usuario_actual)):
    """Tipos dentro del alcance y datos que requiere cada uno."""
    return listar_plantillas()


@router.post("/interpretar", response_model=InterpretacionResponse)
def endpoint_interpretar(request: InterpretacionRequest,
                         usuario: Usuario = Depends(usuario_actual)):
    """Lee un pedido en lenguaje natural y devuelve los datos de la plantilla.

    No redacta ni guarda nada: deja el formulario listo. Con `datos` en el cuerpo, el
    texto completa ese formulario en lugar de empezar uno nuevo.
    """
    try:
        return interpretar_pedido(request.texto, request.tipo_documento, request.datos)
    except (GeneracionNoDisponibleError, InterpretacionNoDisponibleError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@router.post("", response_model=DocumentoGeneradoResponse, status_code=status.HTTP_201_CREATED)
def endpoint_generar(request: GeneracionRequest, db: Session = Depends(get_db),
                     usuario: Usuario = Depends(usuario_actual)):
    try:
        return generar(db, usuario.id, request.tipo_documento, request.datos)
    except TipoFueraDeAlcanceError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except GeneracionNoDisponibleError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@router.get("", response_model=list[DocumentoGeneradoResponse])
def endpoint_listar(limite: int = Query(50, ge=1, le=100), db: Session = Depends(get_db),
                    usuario: Usuario = Depends(usuario_actual)):
    return listar(db, usuario.id, limite)


@router.get("/{id}", response_model=DocumentoGeneradoResponse)
def endpoint_obtener(id: UUID, db: Session = Depends(get_db),
                     usuario: Usuario = Depends(usuario_actual)):
    try:
        return obtener(db, id, usuario.id)
    except DocumentoGeneradoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/{id}/exportar")
def endpoint_exportar(id: UUID, formato: FormatoBorrador = Query(...),
                      db: Session = Depends(get_db),
                      usuario: Usuario = Depends(usuario_actual)):
    """Descarga el borrador en Word o PDF, tal como está guardado."""
    try:
        contenido, nombre, tipo = exportar(db, id, usuario.id, formato)
    except DocumentoGeneradoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    # El nombre lo arma el exportador: solo letras, números, guiones bajos y la extensión.
    return Response(content=contenido, media_type=tipo, headers={
        "Content-Disposition": f'attachment; filename="{nombre}"',
        "Access-Control-Expose-Headers": "Content-Disposition",
    })


@router.get("/{id}/versiones", response_model=list[VersionResumen])
def endpoint_versiones(id: UUID, db: Session = Depends(get_db),
                       usuario: Usuario = Depends(usuario_actual)):
    try:
        return versiones(db, id, usuario.id)
    except DocumentoGeneradoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/{id}/revisiones", response_model=DocumentoGeneradoResponse,
             status_code=status.HTTP_201_CREATED)
def endpoint_revisar(id: UUID, request: RevisionRequest, db: Session = Depends(get_db),
                     usuario: Usuario = Depends(usuario_actual)):
    """Crea una versión nueva; la anterior se conserva."""
    try:
        return revisar(db, id, usuario.id, request.instruccion, request.datos, request.contenido)
    except DocumentoGeneradoNoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except GeneracionNoDisponibleError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
