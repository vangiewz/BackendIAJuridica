import re
import uuid
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.main import app
from app.core.database import get_db
from app.models.auth.usuario import Usuario, RolUsuario
from app.services.conocimiento.perfiles_fuente import PerfilFuente, perfil_de, PERFILES
from app.controllers.conocimiento.ingesta_controller import ingerir_contenido
from app.controllers.conocimiento.errores import FuenteNoProcesableError

client = TestClient(app)

# PDF valido y minimo, sin capa de texto: mismo recurso que usan los tests de documentos.
PDF_SIN_TEXTO = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /Resources <<>> /MediaBox [0 0 612 792] >>\nendobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
    b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n212\n%%EOF\n"
)

PERFIL_FALSO = PerfilFuente(
    codigo="Codigo de Prueba",
    fuente_nombre="Test",
    fuente_url="https://test.local/x.pdf",
    archivo="x.pdf",
    total_esperado=1,
    ruido=re.compile(r"^$"),
    inicio_articulo=re.compile(r"^ART"),
    nivel=re.compile(r"^$"),
)


# --- Registro de perfiles (offline) ---

def test_el_registro_expone_el_codigo_civil():
    assert "codigo_civil" in PERFILES
    assert perfil_de("codigo_civil") is PERFILES["codigo_civil"]


def test_una_fuente_desconocida_no_tiene_perfil():
    assert perfil_de("codigo_penal") is None


# --- Lectura del PDF subido (offline: falla antes de tocar la base) ---

def test_un_archivo_que_no_es_pdf_no_es_procesable():
    with pytest.raises(FuenteNoProcesableError):
        ingerir_contenido(None, PERFIL_FALSO, b"esto no es un pdf", datetime.now(timezone.utc))


def test_un_pdf_sin_capa_de_texto_no_es_procesable():
    with pytest.raises(FuenteNoProcesableError):
        ingerir_contenido(None, PERFIL_FALSO, PDF_SIN_TEXTO, datetime.now(timezone.utc))


# --- Endpoint admin (integracion) ---

def _crear_usuario(rol: RolUsuario) -> dict:
    """Registra un usuario y, si hace falta, le cambia el rol en la base.

    El registro publico siempre crea CIUDADANO: no hay forma de pedir otro rol
    por la API, asi que para probar admin/profesional se promueve aca.
    """
    correo = f"test_admin_{uuid.uuid4()}@ejemplo.com"
    client.post(
        "/api/v1/auth/registro",
        json={"email": correo, "nombre": "Tester Rol", "password": "password123"},
    )

    if rol is not RolUsuario.CIUDADANO:
        db = next(get_db())
        try:
            db.execute(update(Usuario).where(Usuario.email == correo).values(rol=rol))
            db.commit()
        finally:
            db.close()

    login = client.post("/api/v1/auth/login", json={"email": correo, "password": "password123"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.fixture
def headers_admin():
    return _crear_usuario(RolUsuario.ADMINISTRADOR)


@pytest.fixture
def headers_ciudadano():
    return _crear_usuario(RolUsuario.CIUDADANO)


@pytest.fixture
def headers_profesional():
    return _crear_usuario(RolUsuario.PROFESIONAL)


@pytest.mark.integracion
def test_ingestar_sin_token_devuelve_401():
    respuesta = client.post("/api/v1/admin/normativa/ingestas", data={"fuente": "codigo_civil"})
    assert respuesta.status_code == 401


@pytest.mark.integracion
def test_ciudadano_no_puede_ingestar(headers_ciudadano):
    respuesta = client.post(
        "/api/v1/admin/normativa/ingestas",
        data={"fuente": "codigo_civil"},
        headers=headers_ciudadano,
    )
    assert respuesta.status_code == 403


@pytest.mark.integracion
def test_profesional_no_puede_ingestar(headers_profesional):
    respuesta = client.post(
        "/api/v1/admin/normativa/ingestas",
        data={"fuente": "codigo_civil"},
        headers=headers_profesional,
    )
    assert respuesta.status_code == 403


@pytest.mark.integracion
def test_ciudadano_no_puede_listar_fuentes(headers_ciudadano):
    assert client.get("/api/v1/admin/normativa/fuentes", headers=headers_ciudadano).status_code == 403


@pytest.mark.integracion
def test_admin_lista_las_fuentes_soportadas(headers_admin):
    respuesta = client.get("/api/v1/admin/normativa/fuentes", headers=headers_admin)

    assert respuesta.status_code == 200
    claves = [f["clave"] for f in respuesta.json()]
    assert "codigo_civil" in claves


@pytest.mark.integracion
def test_admin_con_fuente_no_soportada_recibe_400(headers_admin):
    respuesta = client.post(
        "/api/v1/admin/normativa/ingestas",
        data={"fuente": "codigo_penal"},
        headers=headers_admin,
    )
    assert respuesta.status_code == 400


@pytest.mark.integracion
def test_admin_con_pdf_invalido_recibe_422(headers_admin):
    respuesta = client.post(
        "/api/v1/admin/normativa/ingestas",
        data={"fuente": "codigo_civil"},
        files={"archivo": ("falso.pdf", b"no soy un pdf", "application/pdf")},
        headers=headers_admin,
    )
    assert respuesta.status_code == 422


@pytest.mark.integracion
def test_admin_con_pdf_sin_texto_recibe_422(headers_admin):
    respuesta = client.post(
        "/api/v1/admin/normativa/ingestas",
        data={"fuente": "codigo_civil"},
        files={"archivo": ("escaneado.pdf", PDF_SIN_TEXTO, "application/pdf")},
        headers=headers_admin,
    )
    assert respuesta.status_code == 422


@pytest.mark.integracion
def test_admin_ingesta_el_corpus_incluido_y_es_idempotente(headers_admin):
    """Reprocesar el Codigo Civil ya cargado no debe insertar ni versionar nada."""
    respuesta = client.post(
        "/api/v1/admin/normativa/ingestas",
        data={"fuente": "codigo_civil"},
        headers=headers_admin,
    )

    assert respuesta.status_code == 201, respuesta.text
    datos = respuesta.json()

    assert datos["fuente"] == "codigo_civil"
    assert datos["origen"] == "incluido"
    assert datos["total_procesados"] == perfil_de("codigo_civil").total_esperado
    # Idempotencia: el corpus ya estaba ingerido, asi que todo queda sin cambios.
    assert datos["insertadas"] == 0
    assert datos["actualizadas"] == 0
    assert datos["sin_cambios"] == datos["total_procesados"]
    assert datos["por_libro"]
    assert datos["por_area"]
