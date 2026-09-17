from typing import Literal
from pydantic import BaseModel

class HealthResponse(BaseModel):
    """Esquema para la respuesta del endpoint de salud."""
    status: Literal["ok"]
    app_name: str
    version: str
    environment: str
    database: Literal["ok", "error", "no configurada"]
