import pytest
import uuid
import os
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def _base_real():
    """Estos tests necesitan Postgres de verdad."""
    previos = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.update(previos)

@pytest.fixture
def auth_headers():
    correo = f"test_{uuid.uuid4()}@ejemplo.com"
    client.post(
        "/api/v1/auth/registro",
        json={"email": correo, "nombre": "Tester", "password": "password123"}
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": correo, "password": "password123"}
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def auth_headers_otro():
    correo = f"test_otro_{uuid.uuid4()}@ejemplo.com"
    client.post(
        "/api/v1/auth/registro",
        json={"email": correo, "nombre": "Tester Otro", "password": "password123"}
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": correo, "password": "password123"}
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.mark.integracion
def test_post_documento_sin_token_devuelve_401():
    response = client.post("/api/v1/documentos")
    assert response.status_code == 401

@pytest.mark.integracion
def test_post_documento_extension_invalida_devuelve_415(auth_headers):
    # xlsx no soportado
    files = {"archivo": ("test.xlsx", b"dummy content", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    response = client.post("/api/v1/documentos", files=files, headers=auth_headers)
    assert response.status_code == 415

@pytest.mark.integracion
def test_post_documento_tamano_excedido_devuelve_413(auth_headers):
    # Generar 11 MB de texto
    content = b"a" * (11 * 1024 * 1024)
    files = {"archivo": ("grande.txt", content, "text/plain")}
    response = client.post("/api/v1/documentos", files=files, headers=auth_headers)
    assert response.status_code == 413

@pytest.mark.integracion
def test_post_documento_codigo_civil(auth_headers):
    ruta_pdf = os.path.join(os.path.dirname(__file__), "..", "data", "normativa", "codigo_civil_oea.pdf")
    with open(ruta_pdf, "rb") as f:
        content = f.read()
    
    files = {"archivo": ("codigo_civil_oea.pdf", content, "application/pdf")}
    response = client.post("/api/v1/documentos", files=files, headers=auth_headers)
    
    assert response.status_code == 201
    data = response.json()
    assert data["estado"] == "completado"
    assert data["cantidad_caracteres"] > 200

@pytest.mark.integracion
def test_post_documento_txt_compraventa(auth_headers):
    texto = b"Este contrato de compraventa establece que el vendedor transfiere al comprador el bien inmueble por el precio convenido. " * 10
    files = {"archivo": ("contrato.txt", texto, "text/plain")}
    response = client.post("/api/v1/documentos", files=files, headers=auth_headers)
    
    assert response.status_code == 201
    data = response.json()
    assert data["estado"] == "completado"
    assert data["tipo_documento"] == "compraventa"
    assert len(data["terminos_detectados"]) > 0

@pytest.mark.integracion
def test_post_documento_pdf_sin_texto(auth_headers):
    # Crear un PDF vacio valido minimo
    pdf_vacio = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /Resources <<>> /MediaBox [0 0 612 792] >>\nendobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
        b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n212\n%%EOF\n"
    )
    files = {"archivo": ("vacio.pdf", pdf_vacio, "application/pdf")}
    response = client.post("/api/v1/documentos", files=files, headers=auth_headers)
    
    assert response.status_code == 201
    data = response.json()
    assert data["estado"] == "fallido"
    assert data["motivo_fallo"] is not None
    assert "texto" in data["motivo_fallo"].lower()

@pytest.mark.integracion
def test_get_documentos_lista(auth_headers):
    # Subir uno
    texto = b"Documento de prueba para listado " * 10
    client.post("/api/v1/documentos", files={"archivo": ("doc1.txt", texto, "text/plain")}, headers=auth_headers)
    
    response = client.get("/api/v1/documentos", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "items" in data
    assert data["total"] >= 1
    assert len(data["items"]) >= 1
    
    # Comprobar que no hay texto_extraido
    assert "texto_extraido" not in data["items"][0]

@pytest.mark.integracion
def test_get_documento_detalle_propio(auth_headers):
    texto_str = "Documento propio de prueba. " * 20
    texto = texto_str.encode("utf-8")
    post_res = client.post("/api/v1/documentos", files={"archivo": ("propio.txt", texto, "text/plain")}, headers=auth_headers)
    doc_id = post_res.json()["id"]
    
    response = client.get(f"/api/v1/documentos/{doc_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == doc_id
    assert "texto_extraido" in data
    assert texto_str.strip() in data["texto_extraido"]


@pytest.mark.integracion
def test_get_documento_otro_usuario_devuelve_404(auth_headers, auth_headers_otro):
    texto = b"Documento secreto."
    post_res = client.post("/api/v1/documentos", files={"archivo": ("secreto.txt", texto, "text/plain")}, headers=auth_headers)
    doc_id = post_res.json()["id"]
    
    response = client.get(f"/api/v1/documentos/{doc_id}", headers=auth_headers_otro)
    assert response.status_code == 404
