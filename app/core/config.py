from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

class Settings(BaseSettings):
    """Configuración principal de la aplicación."""
    app_name: str = "Asistencia Juridica Civil Boliviana"
    app_version: str = "0.1.0"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = ""        # viene de DATABASE_URL en el .env
    jwt_secret: str = ""
    jwt_algoritmo: str = "HS256"
    jwt_access_minutos: int = 30
    jwt_refresh_dias: int = 7
    
    model_config = SettingsConfigDict(env_file=".env")

    @model_validator(mode="after")
    def validate_jwt_secret(self) -> 'Settings':
        if not self.jwt_secret:
            if self.environment == "development":
                import logging
                import secrets
                logging.warning("JWT_SECRET no configurado. Generando uno aleatorio para desarrollo.")
                self.jwt_secret = secrets.token_urlsafe(32)
            else:
                raise ValueError("JWT_SECRET es obligatorio en entornos que no son de desarrollo.")
        return self

@lru_cache()
def get_settings() -> Settings:
    """Instancia cacheada de las configuraciones del sistema."""
    return Settings()
