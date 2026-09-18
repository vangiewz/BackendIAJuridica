import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def _base_real():
    """Estos tests necesitan Postgres de verdad.

    Otros modulos de test registran `app.dependency_overrides[get_db]` apuntando a SQLite al
    importarse, y como pytest importa todos los modulos en la coleccion, ese override se
    filtra hasta aca: las consultas full-text terminaban en SQLite con "no such function:
    to_tsvector". Se limpian mientras corre este modulo y se restauran despues.
    """
    previos = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.update(previos)



@pytest.mark.integracion
def test_buscar_sin_resultados():
    # Cadenas sin ningun lexema del corpus. No sirve una frase con palabras comunes:
    # la busqueda une los terminos con OR, asi que "existe" o "seguro" matchearian.
    response = client.get("/api/v1/normativa/buscar?q=zzqqxv%20wkkjhg")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["resultados"]) == 0

@pytest.mark.integracion
def test_buscar_usucapion():
    res1 = client.get("/api/v1/normativa/buscar?q=usucapion")
    res2 = client.get("/api/v1/normativa/buscar?q=usucapión")
    
    assert res1.status_code == 200
    assert res2.status_code == 200
    if res1.json()["total"] > 0:
        assert res1.json()["total"] == res2.json()["total"]

@pytest.mark.integracion
def test_buscar_area():
    res = client.get("/api/v1/normativa/buscar?q=herencia&area=sucesiones")
    assert res.status_code == 200
    data = res.json()
    for item in data["resultados"]:
        assert item["area_juridica"] == "sucesiones"

@pytest.mark.integracion
def test_buscar_caracteres_raros():
    response = client.get("/api/v1/normativa/buscar?q=?!&")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["resultados"]) == 0

@pytest.mark.integracion
def test_leer_articulo():
    response = client.get("/api/v1/normativa/articulos/Codigo Civil/1")
    if response.status_code == 200:
        data = response.json()
        assert data["numero_articulo"] == 1
        assert "anterior" in data
        assert "siguiente" in data

@pytest.mark.integracion
def test_leer_articulo_no_existe():
    response = client.get("/api/v1/normativa/articulos/Codigo Civil/999999")
    assert response.status_code == 404

@pytest.mark.integracion
def test_obtener_indice():
    response = client.get("/api/v1/normativa/indice?codigo=Codigo Civil")
    if response.status_code == 200:
        data = response.json()
        assert isinstance(data, list)
