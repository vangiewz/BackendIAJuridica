import uuid
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from app.core.config import get_settings
from app.models.auth.usuario import RolUsuario

class TokenInvalido(Exception):
    """Excepción lanzada cuando un token JWT es inválido, expirado o de tipo incorrecto."""
    pass

def hashear_password(password: str) -> str:
    """Genera el hash bcrypt de una contraseña."""
    salt = bcrypt.gensalt()
    # bcrypt devuelve bytes, se guardan como string (utf-8)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verificar_password(password: str, password_hash: str) -> bool:
    """Verifica una contraseña contra su hash."""
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8")
        )
    except ValueError:
        return False

def crear_access_token(usuario_id: uuid.UUID, rol: RolUsuario) -> str:
    """Token corto de acceso. Claims: sub, rol, exp, tipo='access'."""
    settings = get_settings()
    ahora = datetime.now(timezone.utc)
    expiracion = ahora + timedelta(minutes=settings.jwt_access_minutos)
    
    payload = {
        "sub": str(usuario_id),
        "rol": rol.value,
        "exp": expiracion,
        "tipo": "access"
    }
    
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algoritmo)

def crear_refresh_token(usuario_id: uuid.UUID) -> str:
    """Token largo de renovacion. Claims: sub, exp, tipo='refresh'."""
    settings = get_settings()
    ahora = datetime.now(timezone.utc)
    expiracion = ahora + timedelta(days=settings.jwt_refresh_dias)
    
    payload = {
        "sub": str(usuario_id),
        "exp": expiracion,
        "tipo": "refresh"
    }
    
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algoritmo)

def decodificar_token(token: str, tipo_esperado: str) -> dict:
    """Valida firma, expiracion y tipo. Lanza TokenInvalido si algo falla."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algoritmo]
        )
        if payload.get("tipo") != tipo_esperado:
            raise TokenInvalido(f"Tipo de token incorrecto. Se esperaba {tipo_esperado}")
        return payload
    except jwt.ExpiredSignatureError:
        raise TokenInvalido("El token ha expirado")
    except jwt.PyJWTError:
        raise TokenInvalido("Firma de token inválida")
