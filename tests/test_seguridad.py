import uuid
import pytest
from app.core.seguridad import (
    hashear_password, 
    verificar_password, 
    crear_access_token, 
    crear_refresh_token, 
    decodificar_token,
    TokenInvalido
)
from app.models.auth.usuario import RolUsuario

def test_hash_y_verificacion_password():
    password_plano = "mi_super_secreto123"
    hash_generado = hashear_password(password_plano)
    
    assert password_plano != hash_generado
    assert verificar_password(password_plano, hash_generado) is True
    assert verificar_password("otra_password", hash_generado) is False

def test_ciclo_vida_token():
    usuario_id = uuid.uuid4()
    
    # Access token
    access_token = crear_access_token(usuario_id, RolUsuario.CIUDADANO)
    payload_access = decodificar_token(access_token, tipo_esperado="access")
    assert payload_access["sub"] == str(usuario_id)
    assert payload_access["tipo"] == "access"
    assert payload_access["rol"] == RolUsuario.CIUDADANO.value
    
    # Refresh token
    refresh_token = crear_refresh_token(usuario_id)
    payload_refresh = decodificar_token(refresh_token, tipo_esperado="refresh")
    assert payload_refresh["sub"] == str(usuario_id)
    assert payload_refresh["tipo"] == "refresh"
    
    # Token de tipo incorrecto
    with pytest.raises(TokenInvalido):
        decodificar_token(access_token, tipo_esperado="refresh")
        
    with pytest.raises(TokenInvalido):
        decodificar_token(refresh_token, tipo_esperado="access")
