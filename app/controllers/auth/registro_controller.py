from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.auth.usuario import Usuario, RolUsuario
from app.models.auth.esquemas import RegistroRequest, UsuarioResponse
from app.core.seguridad import hashear_password

class EmailYaRegistradoError(Exception):
    """Excepción lanzada cuando el email ya está en uso."""
    pass

def registrar_usuario(db: Session, request: RegistroRequest) -> Usuario:
    """Caso de uso: registrar un nuevo usuario."""
    # Verificar si el email ya existe
    stmt = select(Usuario).where(Usuario.email == request.email)
    existente = db.execute(stmt).scalar_one_or_none()
    
    if existente:
        raise EmailYaRegistradoError(f"El email {request.email} ya está registrado")
    
    # Crear usuario
    nuevo_usuario = Usuario(
        email=request.email,
        nombre=request.nombre,
        password_hash=hashear_password(request.password),
        rol=RolUsuario.CIUDADANO
    )
    
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)
    
    return nuevo_usuario
