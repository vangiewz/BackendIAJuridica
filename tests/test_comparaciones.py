import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# Cada clausula es larga a proposito: al recortar la tercera, el documento resultante
# tiene que seguir superando el minimo de caracteres del extractor, o entraria como
# 'fallido' y el test estaria probando otra cosa.
BASE = """CONTRATO DE ARRENDAMIENTO DE BIEN INMUEBLE

CLAUSULA PRIMERA.- El ARRENDADOR entrega en alquiler el departamento ubicado en la zona
Norte de la ciudad, con una superficie aproximada de ciento veinte metros cuadrados, en
las condiciones de habitabilidad que la ARRENDATARIA declara conocer y aceptar.

CLAUSULA SEGUNDA.- El canon mensual de arrendamiento es de Bs. 3.500.- pagadero por
adelantado dentro de los primeros cinco dias de cada mes, en el domicilio del ARRENDADOR
o mediante transferencia bancaria a la cuenta que este indique por escrito.

CLAUSULA TERCERA.- El plazo del contrato es de 12 meses computables desde la entrega
efectiva del inmueble, prorrogable por acuerdo escrito de ambas partes contratantes.
"""


@pytest.fixture(autouse=True)
def _base_real():
    """Estos tests necesitan Postgres de verdad."""
    previos = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.update(previos)


def _headers_de_usuario_nuevo() -> dict:
    correo = f"test_cmp_{uuid.uuid4()}@ejemplo.com"
    client.post(
        "/api/v1/auth/registro",
        json={"email": correo, "nombre": "Tester Comparacion", "password": "password123"},
    )
    login = client.post("/api/v1/auth/login", json={"email": correo, "password": "password123"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.fixture
def auth_headers():
    return _headers_de_usuario_nuevo()


@pytest.fixture
def auth_headers_otro():
    return _headers_de_usuario_nuevo()


def _subir(headers: dict, nombre: str, texto: str) -> str:
    respuesta = client.post(
        "/api/v1/documentos",
        files={"archivo": (nombre, texto.encode("utf-8"), "text/plain")},
        headers=headers,
    )
    assert respuesta.status_code == 201, respuesta.text
    # Si el texto de prueba fuera demasiado corto entraria como 'fallido' y la
    # comparacion respondería 409: mejor fallar aca, donde se ve el motivo.
    assert respuesta.json()["estado"] == "completado", respuesta.text
    return respuesta.json()["id"]


def _comparar(headers: dict, id_a: str, id_b: str):
    return client.post(
        "/api/v1/documentos/comparaciones",
        json={"documento_a_id": id_a, "documento_b_id": id_b},
        headers=headers,
    )


@pytest.mark.integracion
def test_comparar_sin_token_devuelve_401():
    respuesta = _comparar({}, str(uuid.uuid4()), str(uuid.uuid4()))
    assert respuesta.status_code == 401


@pytest.mark.integracion
def test_comparar_detecta_modificacion_de_monto(auth_headers):
    id_a = _subir(auth_headers, "v1.txt", BASE)
    id_b = _subir(auth_headers, "v2.txt", BASE.replace("Bs. 3.500", "Bs. 4.200"))

    respuesta = _comparar(auth_headers, id_a, id_b)
    assert respuesta.status_code == 201, respuesta.text
    datos = respuesta.json()

    assert datos["nombre_a"] == "v1.txt"
    assert datos["nombre_b"] == "v2.txt"
    assert datos["estrategia"] == "clausulas"
    assert datos["cantidad_cambios"] == 1

    diferencia = datos["diferencias"][0]
    assert diferencia["tipo"] == "modificado"
    assert diferencia["ubicacion"] == "Cláusula SEGUNDA"
    assert diferencia["explicacion"] == "El monto cambió de Bs. 3.500 a Bs. 4.200."


@pytest.mark.integracion
def test_comparar_detecta_clausula_agregada(auth_headers):
    id_a = _subir(auth_headers, "v1.txt", BASE)
    id_b = _subir(auth_headers, "v2.txt", BASE + "\nCLAUSULA CUARTA.- Se pacta deposito en garantia.\n")

    datos = _comparar(auth_headers, id_a, id_b).json()
    agregados = [d for d in datos["diferencias"] if d["tipo"] == "agregado"]

    assert len(agregados) == 1
    assert agregados[0]["ubicacion"] == "Cláusula CUARTA"
    assert agregados[0]["texto_anterior"] is None


@pytest.mark.integracion
def test_comparar_detecta_clausula_eliminada(auth_headers):
    id_a = _subir(auth_headers, "completo.txt", BASE)
    id_b = _subir(auth_headers, "recortado.txt", BASE.split("CLAUSULA TERCERA")[0])

    datos = _comparar(auth_headers, id_a, id_b).json()
    eliminados = [d for d in datos["diferencias"] if d["tipo"] == "eliminado"]

    assert len(eliminados) == 1
    assert eliminados[0]["ubicacion"] == "Cláusula TERCERA"
    assert eliminados[0]["texto_nuevo"] is None


@pytest.mark.integracion
def test_comparar_documentos_identicos_no_devuelve_diferencias(auth_headers):
    id_a = _subir(auth_headers, "a.txt", BASE)
    id_b = _subir(auth_headers, "b.txt", BASE)

    datos = _comparar(auth_headers, id_a, id_b).json()

    assert datos["cantidad_cambios"] == 0
    assert datos["diferencias"] == []


@pytest.mark.integracion
def test_comparar_el_mismo_documento_devuelve_400(auth_headers):
    id_a = _subir(auth_headers, "unico.txt", BASE)

    respuesta = _comparar(auth_headers, id_a, id_a)

    assert respuesta.status_code == 400


@pytest.mark.integracion
def test_comparar_documento_inexistente_devuelve_404(auth_headers):
    id_a = _subir(auth_headers, "existe.txt", BASE)

    respuesta = _comparar(auth_headers, id_a, str(uuid.uuid4()))

    assert respuesta.status_code == 404


@pytest.mark.integracion
def test_no_se_puede_comparar_el_documento_de_otro_usuario(auth_headers, auth_headers_otro):
    id_propio = _subir(auth_headers, "propio.txt", BASE)
    id_ajeno = _subir(auth_headers_otro, "ajeno.txt", BASE.replace("Bs. 3.500", "Bs. 9.900"))

    respuesta = _comparar(auth_headers, id_propio, id_ajeno)

    # El documento de otro usuario no existe para este: 404, no 403, para no confirmar su id.
    assert respuesta.status_code == 404


@pytest.mark.integracion
def test_comparar_documento_sin_texto_devuelve_409(auth_headers):
    id_a = _subir(auth_headers, "bueno.txt", BASE)

    # Un PDF valido sin capa de texto queda en estado 'fallido' y sin texto extraido.
    pdf_sin_texto = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /Resources <<>> /MediaBox [0 0 612 792] >>\nendobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
        b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n212\n%%EOF\n"
    )
    subida = client.post(
        "/api/v1/documentos",
        files={"archivo": ("escaneado.pdf", pdf_sin_texto, "application/pdf")},
        headers=auth_headers,
    )
    assert subida.json()["estado"] == "fallido"
    id_fallido = subida.json()["id"]

    respuesta = _comparar(auth_headers, id_a, id_fallido)

    assert respuesta.status_code == 409
