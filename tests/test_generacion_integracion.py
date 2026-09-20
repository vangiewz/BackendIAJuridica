"""HU-14 y HU-15 contra la base real. El versionado se prueba sin depender de Ollama."""
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.ia.ollama_client import IAError, OllamaClient

client = TestClient(app)


@pytest.fixture
def auth_headers():
    correo = f"gen_{uuid.uuid4()}@ejemplo.com"
    credenciales = {"email": correo, "password": "Password123!"}
    client.post("/api/v1/auth/registro", json={**credenciales, "nombre": "Prueba generación"})
    token = client.post("/api/v1/auth/login", json=credenciales).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


DATOS = {
    "arrendador_nombre": "Luis Mamani Quispe", "arrendador_ci": "4567890 SC",
    "arrendatario_nombre": "Ana Rojas Vaca", "arrendatario_ci": "9876543 SC",
    "lugar": "Santa Cruz de la Sierra", "fecha": "10 de marzo de 2026",
    "inmueble": "Departamento 3B, calle Independencia 45",
    "canon": "2500 bolivianos mensuales", "plazo": "12 meses",
}


@pytest.mark.integracion
def test_plantillas_declaran_el_alcance(auth_headers):
    datos = client.get("/api/v1/documentos-generados/plantillas", headers=auth_headers).json()
    tipos = {p["tipo_documento"] for p in datos}
    assert tipos == {"compraventa", "arrendamiento", "prestamo"}
    for plantilla in datos:
        assert plantilla["campos"] and plantilla["clausulas"]


@pytest.mark.integracion
def test_generacion_sin_token():
    assert client.post("/api/v1/documentos-generados",
                       json={"tipo_documento": "arrendamiento", "datos": {}}).status_code == 401


@pytest.mark.integracion
def test_tipo_fuera_del_alcance_se_rechaza(auth_headers):
    respuesta = client.post("/api/v1/documentos-generados", headers=auth_headers,
                            json={"tipo_documento": "otro", "datos": {}})
    assert respuesta.status_code == 422


def _crear_manual(headers, contenido):
    """Siembra una versión sin pasar por el modelo, para probar solo el versionado."""
    from app.controllers.generacion.documentos_controller import _guardar
    from app.core.database import get_db
    from app.models.auth.usuario import Usuario
    from app.models.shared.enums import TipoDocumento
    from sqlalchemy import select
    db = next(get_db())
    try:
        correo = client.get("/api/v1/auth/yo", headers=headers).json()["email"]
        usuario = db.scalar(select(Usuario).where(Usuario.email == correo))
        fila = _guardar(db, usuario.id, TipoDocumento.ARRENDAMIENTO, contenido)
        return str(fila.id)
    finally:
        db.close()


@pytest.mark.integracion
def test_una_revision_crea_version_nueva_sin_borrar_la_anterior(auth_headers):
    original = "CONTRATO DE ARRENDAMIENTO\n\nPlazo del contrato: 12 meses\n"
    documento_id = _crear_manual(auth_headers, original)

    editado = original.replace("12 meses", "24 meses")
    revision = client.post(f"/api/v1/documentos-generados/{documento_id}/revisiones",
                           json={"contenido": editado}, headers=auth_headers)
    assert revision.status_code == 201, revision.text
    nueva = revision.json()
    assert nueva["version"] == 2
    assert nueva["documento_padre_id"] == documento_id
    assert "24 meses" in nueva["contenido"]

    # La versión anterior sigue intacta y recuperable.
    previa = client.get(f"/api/v1/documentos-generados/{documento_id}", headers=auth_headers)
    assert previa.status_code == 200
    assert previa.json()["contenido"] == original
    assert previa.json()["version"] == 1

    versiones = client.get(f"/api/v1/documentos-generados/{documento_id}/versiones",
                           headers=auth_headers).json()
    assert [v["version"] for v in versiones] == [1, 2]


@pytest.mark.integracion
def test_una_revision_vacia_se_rechaza(auth_headers):
    documento_id = _crear_manual(auth_headers, "CONTRATO DE ARRENDAMIENTO\n")
    respuesta = client.post(f"/api/v1/documentos-generados/{documento_id}/revisiones",
                            json={}, headers=auth_headers)
    assert respuesta.status_code == 422


@pytest.mark.integracion
def test_un_documento_de_otro_usuario_no_es_accesible(auth_headers):
    documento_id = _crear_manual(auth_headers, "CONTRATO DE ARRENDAMIENTO\n")
    otro = f"otro_{uuid.uuid4()}@ejemplo.com"
    client.post("/api/v1/auth/registro", json={"email": otro, "password": "Password123!",
                                               "nombre": "Otro"})
    token = client.post("/api/v1/auth/login",
                        json={"email": otro, "password": "Password123!"}).json()["access_token"]
    respuesta = client.get(f"/api/v1/documentos-generados/{documento_id}",
                           headers={"Authorization": f"Bearer {token}"})
    assert respuesta.status_code == 404


@pytest.mark.ia_local
@pytest.mark.integracion
@pytest.mark.skipif(os.getenv("RUN_IA_LOCAL") != "1", reason="Activar RUN_IA_LOCAL=1 explícitamente")
def test_generacion_real_no_inventa_datos(auth_headers):
    try:
        OllamaClient().modelos()
    except IAError:
        pytest.skip("Ollama no disponible")
    respuesta = client.post("/api/v1/documentos-generados", headers=auth_headers,
                            json={"tipo_documento": "arrendamiento", "datos": DATOS})
    assert respuesta.status_code == 201, respuesta.text
    contenido = respuesta.json()["contenido"]
    for valor in DATOS.values():
        assert valor in contenido
    # El campo opcional no entregado queda señalado, nunca rellenado, y se reporta
    # para que la interfaz pueda pedirlo: lo ausente se ve, no se completa solo.
    assert "[FALTA: Destino o uso del inmueble]" in contenido
    # Cualquier opcional ausente puede señalarse en la cláusula que lo necesita; lo que
    # nunca puede aparecer es un marcador para un campo que la plantilla no define.
    opcionales_ausentes = {"Día de pago del canon", "Destino o uso del inmueble"}
    faltantes = respuesta.json()["campos_faltantes"]
    assert "Destino o uso del inmueble" in faltantes
    assert set(faltantes) <= opcionales_ausentes

    revision = client.post(
        f"/api/v1/documentos-generados/{respuesta.json()['id']}/revisiones", headers=auth_headers,
        json={"instruccion": "Cambiar el plazo de 12 meses a 24 meses"})
    assert revision.status_code == 201, revision.text
    assert revision.json()["version"] == 2
    assert "24 meses" in revision.json()["contenido"]
