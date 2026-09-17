import uuid
from typing import Literal
from pydantic import BaseModel, EmailStr, Field, field_validator
from app.models.auth.usuario import RolUsuario

# bcrypt rechaza cualquier contrasena de mas de 72 BYTES. No son caracteres: en
# espanol la "n" y los acentos ocupan 2 bytes cada uno, asi que una contrasena de
# 40 caracteres puede pasarse. Sin esta validacion, bcrypt lanza ValueError y el
# registro responde 500 en vez de 422.
MAX_BYTES_PASSWORD = 72

class RegistroRequest(BaseModel):
    """Esquema para la peticion de registro."""
    email: EmailStr
    nombre: str = Field(min_length=2)
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def password_cabe_en_bcrypt(cls, valor: str) -> str:
        """Rechaza en la frontera HTTP lo que bcrypt rechazaria como error interno."""
        if len(valor.encode("utf-8")) > MAX_BYTES_PASSWORD:
            raise ValueError(
                f"La contrasena no puede superar {MAX_BYTES_PASSWORD} bytes; "
                "la n con tilde y las vocales acentuadas ocupan 2 bytes cada una"
            )
        return valor

class LoginRequest(BaseModel):
    """Esquema para la peticion de inicio de sesion."""
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    """Respuesta con los tokens generados."""
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"

class RefreshRequest(BaseModel):
    """Esquema para refrescar un token."""
    refresh_token: str

class UsuarioResponse(BaseModel):
    """Respuesta con la informacion del usuario."""
    id: uuid.UUID
    email: EmailStr
    nombre: str
    rol: RolUsuario
    # NUNCA incluir password_hash
