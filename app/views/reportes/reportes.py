"""HU de reportes dinámicos: pedir un reporte en lenguaje natural.

Todas las rutas exigen sesión y el reporte se calcula siempre sobre el usuario del token:
el identificador no se acepta por parámetro ni por cuerpo.
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencias import usuario_actual
from app.controllers.reportes.reportes_controller import (
    ReporteNoInterpretableError, describir_catalogo, ejecutar_especificacion,
    exportar_reporte, generar_reporte,
)
from app.models.auth.usuario import Usuario
from app.models.reportes.esquemas import (
    EjecucionRequest, ExportacionRequest, ReporteRequest, ReporteResultado,
)
from app.services.reportes.interprete import ReporteNoDisponibleError

router = APIRouter(prefix="/reportes", tags=["reportes"])


@router.get("/catalogo")
def endpoint_catalogo(usuario: Usuario = Depends(usuario_actual)):
    """Entidades y campos sobre los que se puede pedir un reporte."""
    return describir_catalogo()


@router.post("", response_model=ReporteResultado)
def endpoint_generar(request: ReporteRequest, db: Session = Depends(get_db),
                     usuario: Usuario = Depends(usuario_actual)):
    try:
        return generar_reporte(db, usuario.id, request.peticion,
                               request.especificacion_actual)
    except ReporteNoInterpretableError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except ReporteNoDisponibleError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@router.post("/ejecutar", response_model=ReporteResultado)
def endpoint_ejecutar(request: EjecucionRequest, db: Session = Depends(get_db),
                      usuario: Usuario = Depends(usuario_actual)):
    """Ejecuta una especificación armada visualmente. Mismo motor, sin IA de por medio."""
    try:
        return ejecutar_especificacion(db, usuario.id, request.especificacion)
    except ReporteNoInterpretableError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/exportar")
def endpoint_exportar(request: ExportacionRequest, db: Session = Depends(get_db),
                      usuario: Usuario = Depends(usuario_actual)):
    """Descarga el reporte como archivo. Rehace solo la consulta, nunca la interpretación."""
    try:
        contenido, nombre, tipo = exportar_reporte(
            db, usuario.id, request.especificacion, request.formato, request.peticion)
    except ReporteNoInterpretableError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    # El nombre ya viene saneado por el exportador: solo letras, números, guiones y punto.
    return Response(content=contenido, media_type=tipo, headers={
        "Content-Disposition": f'attachment; filename="{nombre}"',
        # Sin esto el navegador no ve el nombre del archivo en una respuesta con fetch.
        "Access-Control-Expose-Headers": "Content-Disposition",
    })
