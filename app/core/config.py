from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Configuración principal de la aplicación."""
    app_name: str = "Asistencia Juridica Civil Boliviana"
    app_version: str = "0.1.0"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = ""        # viene de DATABASE_URL en el .env
    
    model_config = SettingsConfigDict(env_file=".env")

@lru_cache()
def get_settings() -> Settings:
    """Instancia cacheada de las configuraciones del sistema."""
    return Settings()
