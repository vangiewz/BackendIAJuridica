import uuid
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.auth.usuario import Usuario
from app.models.auth.esquemas import LoginRequest, TokenResponse, RefreshRequest
from app.core.seguridad import verificar_password, crear_access_token, crear_refresh_token, decodificar_token, TokenInvalido

class CredencialesInvalidasError(Exception):
    """Excepción lanzada cuando el email o password son incorrectos."""
    pass

class SesionInvalidaError(Exception):
    """Excepción lanzada cuando un refresh token es inválido o el usuario está inactivo."""
    pass

def iniciar_sesion(db: Session, request: LoginRequest) -> TokenResponse:
    """Caso de uso: iniciar sesión con email y contraseña."""
    stmt = select(Usuario).where(Usuario.email == request.email)
    usuario = db.execute(stmt).scalar_one_or_none()
    
    if not usuario:
        raise CredencialesInvalidasError("Email o contraseña incorrectos")
        
    if not verificar_password(request.password, usuario.password_hash):
        raise CredencialesInvalidasError("Email o contraseña incorrectos")
        
    if not usuario.activo:
        raise CredencialesInvalidasError("Usuario inactivo")
        
    return TokenResponse(
        access_token=crear_access_token(usuario.id, usuario.rol),
        refresh_token=crear_refresh_token(usuario.id),
        token_type="bearer"
    )

def refrescar_sesion(db: Session, request: RefreshRequest) -> TokenResponse:
    """Caso de uso: obtener un nuevo access token usando el refresh token."""
    try:
        payload = decodificar_token(request.refresh_token, tipo_esperado="refresh")
        usuario_id_str = payload.get("sub")
        if not usuario_id_str:
            raise SesionInvalidaError("Token malformado")
        usuario_id = uuid.UUID(usuario_id_str)
    except (TokenInvalido, ValueError) as e:
        raise SesionInvalidaError(str(e))
        
    stmt = select(Usuario).where(Usuario.id == usuario_id)
    usuario = db.execute(stmt).scalar_one_or_none()
    
    if not usuario or not usuario.activo:
        raise SesionInvalidaError("Usuario inactivo o no existe")
        
    return TokenResponse(
        access_token=crear_access_token(usuario.id, usuario.rol),
        refresh_token=crear_refresh_token(usuario.id),
        token_type="bearer"
    )
