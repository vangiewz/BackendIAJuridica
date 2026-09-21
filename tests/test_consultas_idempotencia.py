import pytest
import uuid
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def _base_real():
    """Sin esto los tests corren contra SQLite y el verde es falso.

    `test_auth.py` deja `app.dependency_overrides` apuntando a SQLite al importarse, asi
    que en la suite completa este archivo probaria otro motor que el que dice probar.
    """
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
        "nombre": "Test User Idemp"
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
        "nombre": "Otro User Idemp"
    })
    res = client.post("/api/v1/auth/login", json={
        "email": correo,
        "password": password
    })
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.mark.integracion
def test_idempotencia_iniciar_consulta(auth_headers):
    client_op_id = str(uuid.uuid4())
    payload = {
        "texto": "Consulta de prueba idempotencia",
        "client_op_id": client_op_id
    }
    
    # Primera llamada
    res1 = client.post("/api/v1/consultas/iniciar", json=payload, headers=auth_headers)
    assert res1.status_code == 202
    data1 = res1.json()
    assert "id" in data1
    
    # Segunda llamada, mismo client_op_id
    res2 = client.post("/api/v1/consultas/iniciar", json=payload, headers=auth_headers)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["id"] == data1["id"]

@pytest.mark.integracion
def test_repetir_no_crea_una_segunda_fila(auth_headers):
    """La segunda llamada devuelve la existente y NO relanza el procesamiento.

    Relanzarla haria que el modelo corriera dos veces sobre la misma consulta, que es
    justo lo que la idempotencia viene a evitar: el costo esta en `_procesar`, no en
    la fila.
    """
    client_op_id = str(uuid.uuid4())
    payload = {"texto": "Consulta que no debe procesarse dos veces", "client_op_id": client_op_id}

    primera = client.post("/api/v1/consultas/iniciar", json=payload, headers=auth_headers)
    assert primera.status_code == 202
    consulta_id = primera.json()["id"]

    antes = client.get(f"/api/v1/consultas/{consulta_id}", headers=auth_headers).json()

    segunda = client.post("/api/v1/consultas/iniciar", json=payload, headers=auth_headers)
    assert segunda.status_code == 200

    # Una sola fila para esa operacion: el historial no la duplica.
    historial = client.get("/api/v1/consultas/historial", headers=auth_headers).json()
    assert len([i for i in historial["items"] if i["id"] == consulta_id]) == 1

    # Y el procesamiento no volvio a arrancar: la consulta no retrocedio a su etapa inicial.
    despues = client.get(f"/api/v1/consultas/{consulta_id}", headers=auth_headers).json()
    assert despues["creada_en"] == antes["creada_en"]

@pytest.mark.integracion
def test_carrera_entre_el_select_y_el_commit(auth_headers, monkeypatch):
    """Dos peticiones simultaneas: la segunda no ve la fila y choca con la constraint.

    Se simula cegando el SELECT previo una sola vez, que es lo que ocurre cuando la
    otra peticion todavia no hizo commit. La constraint frena el duplicado y el
    endpoint tiene que devolver la consulta que quedo, no un 500.
    """
    from app.views.consultas import consultas as vista
    real = vista.consulta_por_operacion
    llamadas = {"n": 0}

    def ciego(db, usuario_id, client_op_id):
        llamadas["n"] += 1
        return None if llamadas["n"] == 1 else real(db, usuario_id, client_op_id)

    client_op_id = str(uuid.uuid4())
    payload = {"texto": "Consulta en carrera con su gemela", "client_op_id": client_op_id}

    primera = client.post("/api/v1/consultas/iniciar", json=payload, headers=auth_headers)
    assert primera.status_code == 202

    monkeypatch.setattr(vista, "consulta_por_operacion", ciego)
    segunda = client.post("/api/v1/consultas/iniciar", json=payload, headers=auth_headers)

    assert segunda.status_code == 200
    assert segunda.json()["id"] == primera.json()["id"]
    # Dos llamadas: la cegada y la del rescate dentro del except. Con una sola, el 200
    # vino del camino normal y este test no estaria probando la carrera.
    assert llamadas["n"] == 2

@pytest.mark.integracion
def test_idempotencia_distintos_usuarios(auth_headers, auth_headers_otro):
    client_op_id = str(uuid.uuid4())
    payload = {
        "texto": "Consulta de prueba idempotencia",
        "client_op_id": client_op_id
    }
    
    # Usuario 1
    res1 = client.post("/api/v1/consultas/iniciar", json=payload, headers=auth_headers)
    assert res1.status_code == 202
    
    # Usuario 2, mismo client_op_id no debe colisionar
    res2 = client.post("/api/v1/consultas/iniciar", json=payload, headers=auth_headers_otro)
    assert res2.status_code == 202
    assert res1.json()["id"] != res2.json()["id"]

@pytest.mark.integracion
def test_iniciar_sin_client_op_id(auth_headers):
    payload = {
        "texto": "Consulta de prueba sin idemp"
    }
    res1 = client.post("/api/v1/consultas/iniciar", json=payload, headers=auth_headers)
    assert res1.status_code == 202
    
    res2 = client.post("/api/v1/consultas/iniciar", json=payload, headers=auth_headers)
    assert res2.status_code == 202
    assert res1.json()["id"] != res2.json()["id"]

@pytest.mark.integracion
def test_client_op_id_malformado(auth_headers):
    payload = {
        "texto": "Consulta de prueba",
        "client_op_id": "no-es-uuid"
    }
    res = client.post("/api/v1/consultas/iniciar", json=payload, headers=auth_headers)
    assert res.status_code == 422
