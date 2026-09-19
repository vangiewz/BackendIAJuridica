import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

CONTRATO = """CONTRATO DE ARRENDAMIENTO DE BIEN INMUEBLE

CLAUSULA PRIMERA.- El ARRENDADOR entrega en alquiler el departamento ubicado en la zona
Norte de la ciudad, con superficie aproximada de ciento veinte metros cuadrados, en las
condiciones de habitabilidad que la ARRENDATARIA declara conocer y aceptar plenamente.

CLAUSULA SEGUNDA.- El canon mensual de arrendamiento es de Bs. 3.500.- pagadero por
adelantado dentro de los primeros cinco dias de cada mes en el domicilio del ARRENDADOR.

CLAUSULA TERCERA.- El plazo del contrato es de 12 meses computables desde la entrega
efectiva del inmueble, prorrogable por acuerdo escrito de ambas partes contratantes.
"""


@pytest.fixture(autouse=True)
def _base_real():
    previos = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.update(previos)


def _headers() -> dict:
    correo = f"test_hist_{uuid.uuid4()}@ejemplo.com"
    client.post(
        "/api/v1/auth/registro",
        json={"email": correo, "nombre": "Tester Historial", "password": "password123"},
    )
    login = client.post("/api/v1/auth/login", json={"email": correo, "password": "password123"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.fixture
def auth_headers():
    return _headers()


@pytest.fixture
def auth_headers_otro():
    return _headers()


def _subir(headers: dict, nombre: str, texto: str) -> str:
    respuesta = client.post(
        "/api/v1/documentos",
        files={"archivo": (nombre, texto.encode("utf-8"), "text/plain")},
        headers=headers,
    )
    assert respuesta.json()["estado"] == "completado", respuesta.text
    return respuesta.json()["id"]


def _comparar(headers: dict, id_a: str, id_b: str) -> dict:
    respuesta = client.post(
        "/api/v1/documentos/comparaciones",
        json={"documento_a_id": id_a, "documento_b_id": id_b},
        headers=headers,
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


# --- Analisis ya persistido: se relee sin recalcular ---

@pytest.mark.integracion
def test_get_analisis_devuelve_el_guardado_sin_recalcular(auth_headers):
    documento_id = _subir(auth_headers, "contrato.txt", CONTRATO)

    creado = client.post(f"/api/v1/documentos/{documento_id}/analisis", headers=auth_headers)
    assert creado.status_code == 201

    leido = client.get(f"/api/v1/documentos/{documento_id}/analisis", headers=auth_headers)
    assert leido.status_code == 200

    # Mismo analisis, no uno nuevo: el id y la fecha de creacion no cambian.
    assert leido.json()["id"] == creado.json()["id"]
    assert leido.json()["creado_en"] == creado.json()["creado_en"]
    assert leido.json()["clausulas"] == creado.json()["clausulas"]


@pytest.mark.integracion
def test_get_analisis_inexistente_devuelve_404(auth_headers):
    documento_id = _subir(auth_headers, "sin_analisis.txt", CONTRATO)

    respuesta = client.get(f"/api/v1/documentos/{documento_id}/analisis", headers=auth_headers)

    assert respuesta.status_code == 404


@pytest.mark.integracion
def test_no_se_puede_leer_el_analisis_de_otro_usuario(auth_headers, auth_headers_otro):
    documento_id = _subir(auth_headers, "propio.txt", CONTRATO)
    client.post(f"/api/v1/documentos/{documento_id}/analisis", headers=auth_headers)

    respuesta = client.get(f"/api/v1/documentos/{documento_id}/analisis", headers=auth_headers_otro)

    assert respuesta.status_code == 404


# --- Historial de comparaciones ---

@pytest.mark.integracion
def test_listar_comparaciones_sin_token_devuelve_401():
    assert client.get("/api/v1/documentos/comparaciones").status_code == 401


@pytest.mark.integracion
def test_historial_de_comparaciones_vacio(auth_headers):
    respuesta = client.get("/api/v1/documentos/comparaciones", headers=auth_headers)

    assert respuesta.status_code == 200
    assert respuesta.json() == {"total": 0, "items": []}


@pytest.mark.integracion
def test_la_comparacion_aparece_en_el_historial(auth_headers):
    id_a = _subir(auth_headers, "v1.txt", CONTRATO)
    id_b = _subir(auth_headers, "v2.txt", CONTRATO.replace("Bs. 3.500", "Bs. 4.200"))
    creada = _comparar(auth_headers, id_a, id_b)

    respuesta = client.get("/api/v1/documentos/comparaciones", headers=auth_headers)
    assert respuesta.status_code == 200
    datos = respuesta.json()

    assert datos["total"] == 1
    item = datos["items"][0]
    assert item["id"] == creada["id"]
    assert item["nombre_a"] == "v1.txt"
    assert item["nombre_b"] == "v2.txt"
    assert item["cantidad_cambios"] == 1
    assert item["estrategia"] == "clausulas"
    assert item["creada_en"] == creada["creada_en"]


@pytest.mark.integracion
def test_reabrir_una_comparacion_devuelve_las_diferencias_guardadas(auth_headers):
    id_a = _subir(auth_headers, "v1.txt", CONTRATO)
    id_b = _subir(auth_headers, "v2.txt", CONTRATO.replace("Bs. 3.500", "Bs. 4.200"))
    creada = _comparar(auth_headers, id_a, id_b)

    respuesta = client.get(f"/api/v1/documentos/comparaciones/{creada['id']}", headers=auth_headers)

    assert respuesta.status_code == 200
    leida = respuesta.json()
    # Byte por byte lo mismo que devolvio la comparacion original.
    assert leida["diferencias"] == creada["diferencias"]
    assert leida["cantidad_cambios"] == creada["cantidad_cambios"]
    assert leida["nombre_a"] == creada["nombre_a"]
    assert leida["creada_en"] == creada["creada_en"]


@pytest.mark.integracion
def test_solo_se_ven_las_comparaciones_propias(auth_headers, auth_headers_otro):
    id_a = _subir(auth_headers, "v1.txt", CONTRATO)
    id_b = _subir(auth_headers, "v2.txt", CONTRATO.replace("12 meses", "24 meses"))
    creada = _comparar(auth_headers, id_a, id_b)

    # El otro usuario no la ve en su listado...
    listado_ajeno = client.get("/api/v1/documentos/comparaciones", headers=auth_headers_otro)
    assert listado_ajeno.json()["total"] == 0

    # ...ni puede abrirla conociendo el id.
    detalle_ajeno = client.get(
        f"/api/v1/documentos/comparaciones/{creada['id']}", headers=auth_headers_otro
    )
    assert detalle_ajeno.status_code == 404


@pytest.mark.integracion
def test_comparacion_inexistente_devuelve_404(auth_headers):
    respuesta = client.get(
        f"/api/v1/documentos/comparaciones/{uuid.uuid4()}", headers=auth_headers
    )
    assert respuesta.status_code == 404


@pytest.mark.integracion
def test_la_ruta_de_comparaciones_no_se_confunde_con_un_documento(auth_headers):
    """/documentos/comparaciones no debe entrar por /documentos/{id}."""
    respuesta = client.get("/api/v1/documentos/comparaciones", headers=auth_headers)

    assert respuesta.status_code == 200
    assert "items" in respuesta.json()


# --- Historial de documentos y consultas (ya existian: se cubre la lectura) ---

@pytest.mark.integracion
def test_el_documento_subido_aparece_en_el_historial_de_documentos(auth_headers):
    documento_id = _subir(auth_headers, "historial.txt", CONTRATO)

    respuesta = client.get("/api/v1/documentos", headers=auth_headers)

    assert respuesta.status_code == 200
    ids = [d["id"] for d in respuesta.json()["items"]]
    assert documento_id in ids


@pytest.mark.integracion
def test_historial_de_consultas_responde_con_total_e_items(auth_headers):
    respuesta = client.get("/api/v1/consultas/historial", headers=auth_headers)

    assert respuesta.status_code == 200
    assert respuesta.json() == {"total": 0, "items": []}
