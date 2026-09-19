from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencias import requiere_rol
from app.models.auth.usuario import RolUsuario
from app.models.conocimiento.esquemas import FuenteDisponible, ReporteIngestaResponse
from app.services.conocimiento.perfiles_fuente import PERFILES, perfil_de
from app.controllers.conocimiento.ingesta_controller import (
    ingerir_fuente, ingerir_contenido, RUTA_DATOS, ReporteIngesta
)
from app.controllers.conocimiento.errores import (
    CorpusIncompletoError, FuenteNoEncontradaError, FuenteNoProcesableError
)

# Solo administradores: la dependencia se aplica a todo el router, asi que ninguna
# ruta nueva puede quedar sin proteger por olvido.
router = APIRouter(
    prefix="/admin/normativa",
    tags=["admin normativa"],
    dependencies=[Depends(requiere_rol(RolUsuario.ADMINISTRADOR))],
)


@router.get("/fuentes", response_model=list[FuenteDisponible])
def listar_fuentes():
    """Fuentes normativas que el sistema sabe procesar."""
    return [
        FuenteDisponible(
            clave=clave,
            codigo=perfil.codigo,
            archivo=perfil.archivo,
            total_esperado=perfil.total_esperado,
            fuente_nombre=perfil.fuente_nombre,
            fuente_url=perfil.fuente_url,
        )
        for clave, perfil in PERFILES.items()
    ]


def _a_respuesta(clave: str, reporte: ReporteIngesta, origen: str) -> ReporteIngestaResponse:
    return ReporteIngestaResponse(
        fuente=clave,
        codigo=reporte.codigo,
        total_procesados=reporte.total_parseados,
        insertadas=reporte.insertadas,
        actualizadas=reporte.actualizadas,
        sin_cambios=reporte.sin_cambios,
        por_libro=reporte.por_libro,
        por_area=reporte.por_area,
        origen=origen,
    )


@router.post("/ingestas", response_model=ReporteIngestaResponse, status_code=status.HTTP_201_CREATED)
async def ingestar(
    fuente: str = Form(..., description="Clave de la fuente, por ejemplo codigo_civil"),
    archivo: UploadFile | None = File(None, description="PDF de la fuente; si falta se usa el incluido"),
    db: Session = Depends(get_db),
):
    """
    Procesa una fuente normativa y la deja consultable.

    Es el mismo pipeline que usa scripts/ingesta_normativa.py: extrae el texto,
    parsea los articulos con su ubicacion y area, y versiona lo que cambio.
    Es idempotente: reprocesar la misma fuente no duplica nada.
    """
    perfil = perfil_de(fuente)
    if perfil is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La fuente '{fuente}' no está soportada.",
        )

    try:
        if archivo is not None and archivo.filename:
            contenido = await archivo.read()
            if not contenido:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El archivo llegó vacío.",
                )
            reporte = ingerir_contenido(db, perfil, contenido, datetime.now(timezone.utc))
            origen = "subido"
        else:
            # Sin archivo se usa el corpus incluido en el repositorio, igual que el CLI.
            reporte = ingerir_fuente(db, perfil, RUTA_DATOS)
            origen = "incluido"
    except FuenteNoProcesableError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except CorpusIncompletoError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except FuenteNoEncontradaError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    db.commit()
    return _a_respuesta(fuente, reporte, origen)
