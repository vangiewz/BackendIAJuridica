from fastapi import APIRouter, Depends
from app.core.config import Settings, get_settings
from app.models.health.estado import HealthResponse
from app.controllers.health.estado_controller import obtener_estado

router = APIRouter(prefix="/health", tags=["health"])

@router.get("", response_model=HealthResponse)
def leer_estado(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Punto de entrada HTTP para verificar la salud del servicio."""
    return obtener_estado(settings)
