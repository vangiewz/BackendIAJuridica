from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencias import usuario_actual
from app.models.auth.usuario import Usuario
from app.models.auth.esquemas import (
    RegistroRequest, 
    LoginRequest, 
    TokenResponse, 
    RefreshRequest, 
    UsuarioResponse
)
from app.controllers.auth.registro_controller import registrar_usuario, EmailYaRegistradoError
from app.controllers.auth.sesion_controller import (
    iniciar_sesion, 
    refrescar_sesion, 
    CredencialesInvalidasError, 
    SesionInvalidaError
)

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/registro", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
def registro(request: RegistroRequest, db: Session = Depends(get_db)):
    """Registra un nuevo usuario en el sistema."""
    try:
        return registrar_usuario(db, request)
    except EmailYaRegistradoError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Inicia sesión y obtiene los tokens de acceso."""
    try:
        return iniciar_sesion(db, request)
    except CredencialesInvalidasError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def refresh(request: RefreshRequest, db: Session = Depends(get_db)):
    """Obtiene un nuevo token de acceso usando el token de refresco."""
    try:
        return refrescar_sesion(db, request)
    except SesionInvalidaError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

@router.get("/yo", response_model=UsuarioResponse, status_code=status.HTTP_200_OK)
def yo(usuario: Usuario = Depends(usuario_actual)):
    """Devuelve la información del usuario autenticado actualmente."""
    return usuario
