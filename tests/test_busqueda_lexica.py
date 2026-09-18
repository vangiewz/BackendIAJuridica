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
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 5
    
    libros = data
    assert libros[0]["desde"] == 1
    assert libros[0]["hasta"] == 73
    assert libros[1]["desde"] == 74
    assert libros[1]["hasta"] == 290
    assert libros[2]["desde"] == 291
    assert libros[2]["hasta"] == 999
    assert libros[3]["desde"] == 1000
    assert libros[3]["hasta"] == 1278
    assert libros[4]["desde"] == 1279
    assert libros[4]["hasta"] == 1570
    
    assert sum(l["cantidad"] for l in libros) == 1570
    
    numeros_vistos = []
    
    def validar_nodo(nodo, padre_desde=None, padre_hasta=None):
        assert nodo["cantidad"] > 0
        assert nodo["desde"] <= nodo["hasta"]
        
        if padre_desde is not None:
            assert nodo["desde"] >= padre_desde
            assert nodo["hasta"] <= padre_hasta
            
        numeros_vistos.extend(nodo.get("numeros", []))
            
        if not nodo.get("hijos"):
            assert len(nodo.get("numeros", [])) == nodo["cantidad"]
        else:
            for hijo in nodo["hijos"]:
                validar_nodo(hijo, nodo["desde"], nodo["hasta"])

    for libro in libros:
        validar_nodo(libro)
        
    assert len(set(numeros_vistos)) == 1570
    assert len(numeros_vistos) == 1570
    
    libro_2 = libros[1]
    titulo_1 = libro_2["hijos"][0]
    cap_unico = titulo_1["hijos"][0]
    # El espacio final importa: sin el, "SECCION I" tambien captura "SECCION II" y "SECCION III",
    # que son las otras dos secciones legitimas de este capitulo.
    secciones = [s for s in cap_unico["hijos"] if s["nombre"].startswith("SECCION I ")]
    assert len(secciones) == 2
    assert secciones[0]["desde"] == 74
    assert secciones[0]["hasta"] == 74
    assert secciones[0]["cantidad"] == 1
    assert secciones[1]["desde"] == 75
    assert secciones[1]["hasta"] == 82
    assert secciones[1]["cantidad"] == 8
    
    libro_3 = libros[2]
    parte_1 = libro_3["hijos"][0]
    titulo_4 = next((t for t in parte_1["hijos"] if t["nombre"].startswith("TITULO IV")), None)
    assert titulo_4 is not None
    assert len(titulo_4["hijos"]) == 3
    caps_t4 = titulo_4["hijos"]
    assert caps_t4[0]["desde"] == 404
    assert caps_t4[0]["hasta"] == 415
    assert caps_t4[1]["desde"] == 416
    assert caps_t4[1]["hasta"] == 426
    assert caps_t4[2]["desde"] == 427
    assert caps_t4[2]["hasta"] == 449
    # Errata de la fuente que se transcribe sin corregir (ADR-009): el tercer capitulo esta
    # impreso como "CAPITULO I" donde corresponderia "CAPITULO III". El espacio final es lo
    # que hace que esta asercion signifique algo.
    assert caps_t4[2]["nombre"].startswith("CAPITULO I ")

    def buscar_nodo(nodos, tipo, texto):
        for n in nodos:
            if n["tipo"] == tipo and texto in n["nombre"].upper():
                return n
            res = buscar_nodo(n.get("hijos", []), tipo, texto)
            if res: return res
        return None

    cap_servidumbres = buscar_nodo(libros, "capitulo", "SERVIDUMBRES FORZOSAS")
    assert cap_servidumbres is not None
    assert cap_servidumbres["numeros"] == [260, 261]
    assert len(cap_servidumbres["hijos"]) == 2

    tit_pruebas = buscar_nodo(libros, "titulo", "DE LAS PRUEBAS EN GENERAL")
    assert tit_pruebas is not None
    assert tit_pruebas["numeros"] == [1283, 1284, 1285, 1286]
    assert len(tit_pruebas["hijos"]) == 7
