import pytest
import uuid
from fastapi.testclient import TestClient
from app.models.documentos.documento import Documento
from app.models.shared.enums import EstadoProceso, TipoDocumento
from app.core.database import get_db
from sqlalchemy import text
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
        json={"email": correo, "nombre": "Tester Contratos", "password": "password123"}
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

@pytest.fixture
def documento_arrendamiento(auth_headers):
    # Crear contrato de arrendamiento sintético
    texto = """CONTRATO DE ARRENDAMIENTO
Entre los suscritos, Juan Pérez con C.I. 1234567 y María Gómez con C.I. 7654321, acuerdan:
PRIMERA.- El objeto del contrato.
SEGUNDA.- El canon mensual será de 1500 bolivianos, pagaderos del 1 al 5.
TERCERA.- El plazo del contrato es de un año.
CUARTA.- El arrendatario no podrá subarrendar sin permiso.
Este contrato no tiene fecha clara ni firmas en este texto de prueba.
"""
    files = {"archivo": ("arrendamiento.txt", texto.encode('utf-8'), "text/plain")}
    response = client.post("/api/v1/documentos", files=files, headers=auth_headers)
    assert response.status_code == 201
    return response.json()

@pytest.mark.integracion
def test_post_analisis_sin_token_devuelve_401():
    response = client.post(f"/api/v1/documentos/{uuid.uuid4()}/analisis")
    assert response.status_code == 401

@pytest.mark.integracion
def test_post_analisis_otro_usuario_devuelve_404(auth_headers_otro, documento_arrendamiento):
    doc_id = documento_arrendamiento["id"]
    response = client.post(f"/api/v1/documentos/{doc_id}/analisis", headers=auth_headers_otro)
    assert response.status_code == 404

@pytest.mark.integracion
def test_post_analisis_documento_fallido(auth_headers):
    # Insertar directo con estado = fallido
    texto = b"No importa"
    post_res = client.post("/api/v1/documentos", files={"archivo": ("fallido.txt", texto, "text/plain")}, headers=auth_headers)
    doc_id = post_res.json()["id"]

    # Cambiar estado a fallido en base de datos
    db = next(get_db())
    doc = db.query(Documento).filter(Documento.id == doc_id).first()
    doc.estado = EstadoProceso.FALLIDO
    db.commit()
    db.close()

    response = client.post(f"/api/v1/documentos/{doc_id}/analisis", headers=auth_headers)
    assert response.status_code == 409

@pytest.mark.integracion
def test_post_analisis_arrendamiento_exito(auth_headers, documento_arrendamiento):
    doc_id = documento_arrendamiento["id"]
    response = client.post(f"/api/v1/documentos/{doc_id}/analisis", headers=auth_headers)
    assert response.status_code == 201

    data = response.json()
    assert data["documento_id"] == doc_id
    assert len(data["clausulas"]) > 0
    assert len(data["hallazgos"]) > 0
    assert len(data["riesgos"]) > 0

    # Riesgo devuelve articulos no vacio
    for r in data["riesgos"]:
        assert len(r["articulos"]) > 0

    # Con la IA desactivada el motor de reglas responde igual: resumen y observaciones
    # quedan vacíos en lugar de inventarse. Los riesgos de arriba no dependen de la IA.
    assert data["resumen"] is None
    assert data["observaciones"] == []

    # Verificar BD
    db = next(get_db())
    count = db.execute(text("SELECT COUNT(*) FROM riesgos_contractuales WHERE analisis_id = :id"), {"id": data["id"]}).scalar()
    db.close()
    assert count == len(data["riesgos"])

@pytest.mark.integracion
def test_post_analisis_no_duplica(auth_headers, documento_arrendamiento):
    doc_id = documento_arrendamiento["id"]
    res1 = client.post(f"/api/v1/documentos/{doc_id}/analisis", headers=auth_headers)
    assert res1.status_code == 201
    data1 = res1.json()

    res2 = client.post(f"/api/v1/documentos/{doc_id}/analisis", headers=auth_headers)
    assert res2.status_code == 201
    data2 = res2.json()

    assert data1["id"] == data2["id"]
    assert len(data1["riesgos"]) == len(data2["riesgos"])

    # Verificar count en base
    db = next(get_db())
    count = db.execute(text("SELECT COUNT(*) FROM riesgos_contractuales WHERE analisis_id = :id"), {"id": data1["id"]}).scalar()
    db.close()
    assert count == len(data1["riesgos"])

@pytest.mark.integracion
def test_get_analisis_sin_analisis_devuelve_404(auth_headers, documento_arrendamiento):
    doc_id = documento_arrendamiento["id"]
    response = client.get(f"/api/v1/documentos/{doc_id}/analisis", headers=auth_headers)
    assert response.status_code == 404

@pytest.mark.integracion
def test_get_analisis_exito(auth_headers, documento_arrendamiento):
    doc_id = documento_arrendamiento["id"]
    post_res = client.post(f"/api/v1/documentos/{doc_id}/analisis", headers=auth_headers)
    assert post_res.status_code == 201

    get_res = client.get(f"/api/v1/documentos/{doc_id}/analisis", headers=auth_headers)
    assert get_res.status_code == 200

    assert post_res.json()["id"] == get_res.json()["id"]
    assert post_res.json()["riesgos"] == get_res.json()["riesgos"]


@pytest.mark.integracion
def test_get_conserva_reglas_evaluadas_y_los_plazos(auth_headers, documento_arrendamiento):
    """El GET reconstruye desde la base: si algo no se persistio, aca se nota."""
    doc_id = documento_arrendamiento["id"]
    post = client.post(f"/api/v1/documentos/{doc_id}/analisis", headers=auth_headers).json()
    get = client.get(f"/api/v1/documentos/{doc_id}/analisis", headers=auth_headers).json()

    # `reglas_evaluadas` son las reglas que corrieron, no los riesgos encontrados. Cuando se
    # calculaba como len(riesgos), el GET informaba menos reglas de las que realmente corrieron
    # y un analisis limpio decia "0 reglas evaluadas".
    assert get["reglas_evaluadas"] == post["reglas_evaluadas"]
    assert get["reglas_evaluadas"] > len(get["riesgos"])

    # Los plazos se perdian: la respuesta se armaba desde las columnas fechas/montos/partes,
    # donde no entran ni los plazos ni los NIT.
    tipos_post = {h["tipo"] for h in post["hallazgos"]}
    tipos_get = {h["tipo"] for h in get["hallazgos"]}
    assert "plazo" in tipos_post
    assert tipos_post == tipos_get
