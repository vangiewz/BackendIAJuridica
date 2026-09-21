from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, model_validator
from urllib.parse import urlsplit
from ipaddress import ip_address
from typing import Literal

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
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"
    ollama_timeout: float = Field(default=180, gt=0, le=600)
    ollama_temperature: float = Field(default=0, ge=0, le=0.3)
    # 8192 deja entrar el prompt del modo simple (fuentes + instrucciones) y una
    # respuesta desarrollada sin que Ollama recorte la salida. Es un valor único
    # para todos los endpoints: cambiar de ventana obliga a recargar el modelo.
    ollama_num_ctx: int = Field(default=8192, ge=2048, le=16384)
    ollama_num_predict: int = Field(default=1800, ge=128, le=4096)
    # Presupuestos por tarea: los borradores conservan el límite general.
    ollama_rag_num_predict: int = Field(default=1100, ge=512, le=4096)
    ollama_short_num_predict: int = Field(default=600, ge=256, le=2048)
    embedding_model: str = "qwen3-embedding:0.6b"
    embedding_num_gpu: int = Field(default=0, ge=0)
    # Medido sobre 12 corridas por variante (docs/benchmarks/topk*_8b*.json): con 3
    # fuentes la respuesta tarda 34,2 s de media frente a 43,8 s con 8, con el mismo
    # grounding (12/12) y la misma abstención. Subirlo a 8 es el ajuste conservador
    # si alguna consulta real necesitara más margen de recuperación.
    rag_top_k: int = Field(default=3, ge=1, le=10)
    ollama_keep_alive: str = "30m"
    embedding_keep_alive: str = "30m"
    ia_explanation_cache_size: int = Field(default=128, ge=0, le=1024)
    ia_explanation_cache_ttl: int = Field(default=1800, ge=0, le=86400)
    rag_candidate_k: int = Field(default=20, ge=10, le=100)
    rag_parallel_embedding: bool = True
    ia_pipeline: Literal["simple", "advanced"] = "simple"
    ia_enabled: bool = True
    # Origenes web autorizados. Van separados por coma porque una variable de entorno no
    # admite listas: el frontend publicado mas los puertos de Expo/Metro en local.
    cors_origins: str = (
        "https://ia-juridica-weld.vercel.app,"
        "http://localhost:8081,http://localhost:19006,http://localhost:3000,"
        "http://localhost:8082,http://localhost:5173,"
        "http://127.0.0.1:8081,http://127.0.0.1:19006,http://127.0.0.1:3000"
    )
    # Cada preview de Vercel estrena subdominio, asi que se autoriza por patron.
    cors_origin_regex: str = r"^https://ia-juridica[\w-]*\.vercel\.app$"

    @property
    def origenes_cors(self) -> list[str]:
        """Lista explicita: el comodin '*' es invalido cuando se permiten credenciales."""
        return [origen.strip().rstrip("/") for origen in self.cors_origins.split(",") if origen.strip()]

    @field_validator("ollama_url")
    @classmethod
    def solo_ollama_local(cls, value: str) -> str:
        url = urlsplit(value)
        try:
            local = url.hostname == "localhost" or ip_address(url.hostname or "").is_loopback
        except ValueError:
            local = False
        if (not local or url.scheme != "http" or url.username or url.password
                or url.path not in ("", "/") or url.query or url.fragment):
            raise ValueError("OLLAMA_URL debe apuntar a HTTP de loopback local sin credenciales")
        return value.rstrip("/")

    @field_validator("ollama_model", "embedding_model")
    @classmethod
    def modelo_local(cls, value: str) -> str:
        if not value.strip() or "cloud" in value.lower() or "://" in value:
            raise ValueError("Se requiere un modelo local, sin variantes cloud")
        return value
    
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
