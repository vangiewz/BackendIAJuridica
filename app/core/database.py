from typing import Iterator, Literal
from sqlalchemy import create_engine, Engine, text
from sqlalchemy.orm import Session, sessionmaker
from app.core.config import Settings, get_settings

def normalizar_url(url: str) -> str:
    """Neon entrega 'postgresql://'; SQLAlchemy 2.x necesita el driver psycopg 3 explicito."""
    if not url:
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

def crear_engine(settings: Settings) -> Engine | None:
    """Devuelve None si no hay DATABASE_URL configurada, para no romper el arranque."""
    url = normalizar_url(settings.database_url)
    if not url:
        return None
    return create_engine(url, pool_pre_ping=True)

_engine: Engine | None = None
_sessionmaker: sessionmaker | None = None

def obtener_engine() -> Engine | None:
    """Engine compartido: Neon cobra por conexion, asi que se crea una sola vez y se reusa."""
    global _engine, _sessionmaker
    if _engine is None:
        settings = get_settings()
        if settings.database_url:
            _engine = crear_engine(settings)
            if _engine:
                _sessionmaker = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine

def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: abre y cierra la sesion por request."""
    eng = obtener_engine()
    if eng is None or _sessionmaker is None:
        raise RuntimeError("DATABASE_URL no esta configurada")

    db = _sessionmaker()
    try:
        yield db
    finally:
        db.close()

def verificar_conexion() -> Literal["ok", "error", "no configurada"]:
    """Ejecuta SELECT 1. Nunca lanza excepcion: reporta 'error' si falla."""
    eng = obtener_engine()
    if eng is None:
        return "no configurada"
    
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"
