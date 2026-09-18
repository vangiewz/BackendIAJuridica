from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.views.health.estado import router as health_router
from app.views.auth.sesion import router as auth_router
from app.views.conocimiento.normativa import router as normativa_router

def create_app() -> FastAPI:
    """Construye y configura la instancia principal de FastAPI."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(auth_router, prefix=settings.api_prefix)
    app.include_router(normativa_router, prefix=settings.api_prefix)
    return app

app = create_app()
