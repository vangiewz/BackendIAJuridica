from fastapi import APIRouter, Depends, Query

from app.core.dependencias import usuario_actual
from app.models.auth.usuario import Usuario
from app.services.ayuda.asistente import (Pantalla, TipoDocumentoAyuda,
                                         SolicitudAyuda, RespuestaAyuda, conversar)
from app.services.ayuda.catalogo import catalogo_para

router = APIRouter(prefix="/ayuda", tags=["Ayuda de la aplicación"])


@router.get("/pantallas/{pantalla}")
def leer_pantalla(pantalla: Pantalla,
                 tipo_documento: TipoDocumentoAyuda | None = Query(default=None),
                 usuario: Usuario = Depends(usuario_actual)):
    return catalogo_para(pantalla, tipo_documento)


@router.post("/chat", response_model=RespuestaAyuda)
def chat_ayuda(solicitud: SolicitudAyuda,
               usuario: Usuario = Depends(usuario_actual)):
    return conversar(solicitud)
