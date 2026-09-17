import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.core.database import get_db
from app.models.shared.base import Base
from app.models.auth.usuario import Usuario, RolUsuario
from app.core.seguridad import hashear_password

# Base en memoria para pruebas. StaticPool es obligatorio: sin el, cada conexion
# abre su propia base vacia y las tablas creadas en una no existen en la siguiente.
SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def test_registro_exitoso():
    response = client.post(
        "/api/v1/auth/registro",
        json={"email": "test@ejemplo.com", "nombre": "Test User", "password": "password123"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@ejemplo.com"
    assert data["rol"] == "ciudadano"
    assert "password_hash" not in data

def test_registro_email_duplicado():
    # Registrar por primera vez
    client.post(
        "/api/v1/auth/registro",
        json={"email": "duplicado@ejemplo.com", "nombre": "Test", "password": "password123"}
    )
    # Intentar segunda vez
    response = client.post(
        "/api/v1/auth/registro",
        json={"email": "duplicado@ejemplo.com", "nombre": "Test2", "password": "password123"}
    )
    assert response.status_code == 409

def test_login_exitoso():
    # Setup usuario
    client.post(
        "/api/v1/auth/registro",
        json={"email": "login@ejemplo.com", "nombre": "Login", "password": "password123"}
    )
    
    # Login
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "login@ejemplo.com", "password": "password123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

def test_login_credenciales_invalidas():
    # Setup usuario
    client.post(
        "/api/v1/auth/registro",
        json={"email": "login2@ejemplo.com", "nombre": "Login", "password": "password123"}
    )
    
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "login2@ejemplo.com", "password": "incorrecta"}
    )
    assert response.status_code == 401

def test_endpoint_protegido():
    # Setup usuario y obtener token
    client.post(
        "/api/v1/auth/registro",
        json={"email": "yo@ejemplo.com", "nombre": "Yo", "password": "password123"}
    )
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "yo@ejemplo.com", "password": "password123"}
    )
    token = login_response.json()["access_token"]
    
    # Endpoint protegido con token
    response = client.get(
        "/api/v1/auth/yo",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == "yo@ejemplo.com"
    
    # Sin token
    response_sin = client.get("/api/v1/auth/yo")
    assert response_sin.status_code == 401


def test_registro_password_larga_en_bytes_devuelve_422():
    """Una contrasena de 40 caracteres con enes son 80 bytes: bcrypt la rechaza.

    Sin la validacion en el esquema esto devuelve 500 en vez de 422.
    """
    response = client.post(
        "/api/v1/auth/registro",
        json={
            "email": "bytes@ejemplo.com",
            "nombre": "Prueba Bytes",
            "password": "ñ" * 40,
        },
    )
    assert response.status_code == 422
