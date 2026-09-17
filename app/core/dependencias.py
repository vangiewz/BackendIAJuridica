import uuid
from typing import Callable, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.core.database import get_db
from app.core.seguridad import decodificar_token, TokenInvalido
from app.models.auth.usuario import Usuario, RolUsuario

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

def usuario_actual(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Usuario:
    """Extrae el Bearer token, lo valida y devuelve el usuario. 401 si falla."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales invalidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = decodificar_token(token, tipo_esperado="access")
        usuario_id_str = payload.get("sub")
        if usuario_id_str is None:
            raise credentials_exception
        usuario_id = uuid.UUID(usuario_id_str)
    except (TokenInvalido, ValueError):
        raise credentials_exception

    stmt = select(Usuario).where(Usuario.id == usuario_id)
    usuario = db.execute(stmt).scalar_one_or_none()
    
    if usuario is None:
        raise credentials_exception
    
    if not usuario.activo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inactivo")
        
    return usuario

def requiere_rol(*roles: RolUsuario) -> Callable[[Usuario], Usuario]:
    """Fabrica de dependencias: 403 si el rol del usuario no esta en la lista."""
    def rol_checker(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
        if usuario.rol not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene los permisos necesarios"
            )
        return usuario
    return rol_checker
