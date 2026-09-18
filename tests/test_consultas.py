import pytest
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.core.database import get_db
from app.models.consultas.consulta import Consulta
from app.models.consultas.fuente_legal import FuenteLegal

client = TestClient(app)

@pytest.fixture(autouse=True)
def _base_real():
    previos = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.update(previos)

@pytest.fixture
def auth_headers():
    correo = f"test_{uuid.uuid4()}@ejemplo.com"
    password = "Password123!"
    client.post("/api/v1/auth/registro", json={
        "email": correo,
        "password": password,
        "nombre": "Test User"
    })
    res = client.post("/api/v1/auth/login", json={
        "email": correo,
        "password": password
    })
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def auth_headers_otro():
    correo = f"test_{uuid.uuid4()}@ejemplo.com"
    password = "Password123!"
    client.post("/api/v1/auth/registro", json={
        "email": correo,
        "password": password,
        "nombre": "Otro User"
    })
    res = client.post("/api/v1/auth/login", json={
        "email": correo,
        "password": password
    })
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.mark.integracion
def test_crear_consulta_sin_token():
    res = client.post("/api/v1/consultas", json={"texto": "Compré un terreno"})
    assert res.status_code == 401

@pytest.mark.integracion
def test_crear_consulta_completa(auth_headers):
    # Con el ejemplo del documento de alcance responde 201, clasifica contratos, 
    # trae terminos_detectados no vacio y al menos 3 fuentes
    texto = "Compré un terreno, pagué todo, pero el vendedor no quiere realizar la transferencia"
    res = client.post("/api/v1/consultas", json={"texto": texto}, headers=auth_headers)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["area_juridica"] == "contratos"
    assert len(data["terminos_detectados"]) > 0
    assert len(data["fuentes"]) >= 3
    assert data["respuesta"] is None
    
    # Fuentes ordenadas
    ordenes = [f["orden"] for f in data["fuentes"]]
    assert ordenes == sorted(ordenes)
    
    # Fuentes traen estado_vigencia y fuente_url
    for f in data["fuentes"]:
        assert "estado_vigencia" in f
        assert "fuente_url" in f
        
    # Las filas quedan realmente en la base
    consulta_id = uuid.UUID(data["id"])
    db = next(get_db())
    try:
        count_fuentes = db.scalar(select(lambda: func.count()).select_from(FuenteLegal).where(FuenteLegal.consulta_id == consulta_id))
        assert count_fuentes == len(data["fuentes"])
    except Exception as e:
        # Fallback to len of execute
        count_fuentes = len(db.execute(select(FuenteLegal).where(FuenteLegal.consulta_id == consulta_id)).all())
        assert count_fuentes == len(data["fuentes"])
    finally:
        db.close()

@pytest.mark.integracion
def test_crear_consulta_sin_clasificacion(auth_headers):
    res = client.post("/api/v1/consultas", json={"texto": "hola, ¿cómo estás?"}, headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["area_juridica"] is None
    
@pytest.mark.integracion
def test_crear_consulta_muy_corta(auth_headers):
    res = client.post("/api/v1/consultas", json={"texto": "aa"}, headers=auth_headers)
    assert res.status_code == 422
    
@pytest.mark.integracion
def test_historial_y_consulta(auth_headers, auth_headers_otro):
    texto = "Consulta para historial sobre terrenos"
    res = client.post("/api/v1/consultas", json={"texto": texto}, headers=auth_headers)
    assert res.status_code == 201
    consulta_id = res.json()["id"]
    
    # GET /consultas/historial devuelve solo las del usuario
    hist = client.get("/api/v1/consultas/historial", headers=auth_headers)
    assert hist.status_code == 200
    hist_data = hist.json()
    assert hist_data["total"] >= 1
    assert any(item["id"] == consulta_id for item in hist_data["items"])
    
    # GET /consultas/{id} de otro usuario devuelve 404
    res_otro = client.get(f"/api/v1/consultas/{consulta_id}", headers=auth_headers_otro)
    assert res_otro.status_code == 404
    
    # GET /consultas/{id} inexistente
    res_inex = client.get(f"/api/v1/consultas/{uuid.uuid4()}", headers=auth_headers)
    assert res_inex.status_code == 404

def test_offline():
    # Solo para asegurar que se pueda correr si no estamos en integracion
    assert True
