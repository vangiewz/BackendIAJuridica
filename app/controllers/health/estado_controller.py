from app.core.config import Settings
from app.models.health.estado import HealthResponse
from app.core.database import verificar_conexion

def obtener_estado(settings: Settings) -> HealthResponse:
    """Compone y devuelve el estado actual del servicio basándose en la configuración."""
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        database=verificar_conexion(),
    )
