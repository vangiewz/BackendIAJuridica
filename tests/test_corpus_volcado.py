import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.core.database import obtener_engine
from app.models.conocimiento.norma import Norma

client = TestClient(app)

# Fuera del rango real del Codigo Civil (1-1570), para que el alta de prueba no
# colisione con la constraint (codigo, numero_articulo, version) ni se confunda con
# un articulo de verdad si algo la deja atras.
NUMERO_POSTIZO = 999999

@pytest.fixture(autouse=True)
def _base_real():
    """Estos tests necesitan Postgres de verdad.

    `test_auth.py` deja `app.dependency_overrides` apuntando a SQLite al importarse;
    limpiarlos es lo que hace que estos tests consulten el corpus real y no otro motor.
    """
    previos = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.update(previos)

@pytest.mark.integracion
def test_corpus_version_consistente():
    r1 = client.get("/api/v1/normativa/corpus/version?codigo=Codigo Civil")
    r2 = client.get("/api/v1/normativa/corpus/version?codigo=Codigo Civil")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()

@pytest.mark.integracion
def test_corpus_version_cambia_al_modificar():
    """La huella se mueve ante un alta, y vuelve a su valor al deshacerla.

    Se da de alta una norma propia en vez de desactivar una del corpus: si el proceso
    muere entre el cambio y su reversa, queda un articulo de prueba identificable por
    su numero, no un hueco silencioso en el Codigo Civil de produccion.
    """
    r1 = client.get("/api/v1/normativa/corpus/version?codigo=Codigo Civil")
    assert r1.status_code == 200
    version_inicial = r1.json()["version"]

    postiza = Norma(
        codigo="Codigo Civil", articulo="Articulo de prueba", numero_articulo=NUMERO_POSTIZO,
        texto="Articulo insertado por test_corpus_volcado; si lo ves en la base, sobra.",
        fuente_nombre="prueba", fuente_url="https://ejemplo.invalid/prueba",
        descargada_en=datetime.now(timezone.utc),
    )
    with Session(obtener_engine()) as db:
        db.add(postiza)
        db.commit()
        id_postizo = postiza.id

    try:
        r2 = client.get("/api/v1/normativa/corpus/version?codigo=Codigo Civil")
        assert r2.status_code == 200
        assert r2.json()["version"] != version_inicial
        assert r2.json()["cantidad"] == r1.json()["cantidad"] + 1
    finally:
        with Session(obtener_engine()) as db:
            sobrante = db.get(Norma, id_postizo)
            if sobrante:
                db.delete(sobrante)
                db.commit()

    # Deshecha el alta, la huella vuelve a ser la misma: es funcion del estado, no del tiempo.
    r3 = client.get("/api/v1/normativa/corpus/version?codigo=Codigo Civil")
    assert r3.json()["version"] == version_inicial

@pytest.mark.integracion
def test_corpus_paginacion():
    v = client.get("/api/v1/normativa/corpus/version?codigo=Codigo Civil")
    assert v.status_code == 200
    total_esperado = v.json()["cantidad"]
    # En la base de test son 1570
    assert total_esperado == 1570

    desde = 0
    limite = 200
    articulos_recibidos = []

    while desde < total_esperado:
        r = client.get(f"/api/v1/normativa/corpus?codigo=Codigo Civil&desde={desde}&limite={limite}")
        assert r.status_code == 200
        data = r.json()
        assert len(data["articulos"]) > 0
        articulos_recibidos.extend(data["articulos"])
        desde += limite

    assert len(articulos_recibidos) == total_esperado
    
    numeros = [a["numero_articulo"] for a in articulos_recibidos]
    assert numeros == sorted(numeros)
    assert len(set(numeros)) == total_esperado

    articulo = articulos_recibidos[0]
    assert "estado_vigencia" in articulo
    assert "fuente_url" in articulo
    assert "busqueda" not in articulo
    assert "embedding" not in articulo

@pytest.mark.integracion
def test_corpus_codigo_inexistente():
    r1 = client.get("/api/v1/normativa/corpus/version?codigo=Inexistente")
    assert r1.status_code == 404
    r2 = client.get("/api/v1/normativa/corpus?codigo=Inexistente&desde=0&limite=200")
    assert r2.status_code == 404

@pytest.mark.integracion
def test_corpus_limite_excedido():
    r = client.get("/api/v1/normativa/corpus?codigo=Codigo Civil&desde=0&limite=501")
    assert r.status_code == 422
