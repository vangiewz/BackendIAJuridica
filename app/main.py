from fastapi import FastAPI
from app.core.config import get_settings
from app.views.health.estado import router as health_router
from app.views.auth.sesion import router as auth_router

def create_app() -> FastAPI:
    """Construye y configura la instancia principal de FastAPI."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
    )
    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(auth_router, prefix=settings.api_prefix)
    return app

app = create_app()
