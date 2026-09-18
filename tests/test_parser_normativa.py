import pytest
from pathlib import Path
from app.services.conocimiento.extractor_pdf import extraer_texto
from app.services.conocimiento.perfiles_fuente import CODIGO_CIVIL
from app.services.conocimiento.parser_articulos import parsear

@pytest.fixture(scope="module")
def articulos_parseados():
    ruta_pdf = Path(__file__).parent.parent / "data" / "normativa" / CODIGO_CIVIL.archivo
    assert ruta_pdf.exists(), f"El archivo {ruta_pdf} no existe."
    texto = extraer_texto(ruta_pdf, CODIGO_CIVIL.ruido)
    return parsear(texto, CODIGO_CIVIL)

def test_cantidad_articulos(articulos_parseados):
    assert len(articulos_parseados) == 1570

def test_numeracion_consecutiva(articulos_parseados):
    numeros = [a.numero for a in articulos_parseados]
    esperado = list(range(1, 1571))
    assert numeros == esperado, "Faltan o sobran articulos, o estan duplicados."

def test_sin_texto_vacio(articulos_parseados):
    for a in articulos_parseados:
        assert a.texto.strip() != "", f"El articulo {a.numero} tiene texto vacio."

def test_estadisticas_jerarquia(articulos_parseados):
    libros = set(a.libro for a in articulos_parseados if a.libro)
    partes = set((a.libro, a.parte) for a in articulos_parseados if a.parte)
    titulos = set((a.libro, a.parte, a.titulo) for a in articulos_parseados if a.titulo)
    capitulos = set((a.libro, a.parte, a.titulo, a.capitulo) for a in articulos_parseados if a.capitulo)
    secciones = set((a.libro, a.parte, a.titulo, a.capitulo, a.seccion) for a in articulos_parseados if a.seccion)

    assert len(libros) == 5, f"Se esperaban 5 libros, hay {len(libros)}"
    assert len(partes) == 2, f"Se esperaban 2 partes, hay {len(partes)}"
    assert len(titulos) == 29, f"Se esperaban 29 titulos, hay {len(titulos)}"
    assert len(capitulos) == 119, f"Se esperaban 119 capitulos, hay {len(capitulos)}"
    assert len(secciones) == 156, f"Se esperaban 156 secciones, hay {len(secciones)}"

def test_epigrafe_multilinea(articulos_parseados):
    art_254 = next(a for a in articulos_parseados if a.numero == 254)
    assert art_254.epigrafe == "APLICACIÓN DE LAS DISPOSICIONES SOBRE EL USUFRUCTO"

def test_casos_erratas(articulos_parseados):
    casos = [149, 191, 578, 1106, 1441]
    for num in casos:
        art = next(a for a in articulos_parseados if a.numero == num)
        assert art.texto.strip() != "", f"El articulo {num} tiene texto vacio."
        if art.epigrafe:
            assert not art.epigrafe.startswith("-")
            assert not art.epigrafe.startswith("(")
            
def test_limites_libros(articulos_parseados):
    art_1 = next(a for a in articulos_parseados if a.numero == 1)
    art_1570 = next(a for a in articulos_parseados if a.numero == 1570)
    assert "LIBRO PRIMERO" in art_1.libro
    assert "LIBRO QUINTO" in art_1570.libro

def test_reinicio_cascada_libro_iv(articulos_parseados):
    art_999 = next(a for a in articulos_parseados if a.numero == 999)
    art_1000 = next(a for a in articulos_parseados if a.numero == 1000)
    
    assert art_999.parte is not None
    assert art_1000.parte is None, "El Libro IV heredo la parte del Libro III"
    assert art_999.titulo != art_1000.titulo, "El Libro IV heredo el titulo del Libro III"

def test_sin_contaminacion_jerarquia(articulos_parseados):
    import re
    regex = re.compile(r' (LIBRO|PARTE|TITULO|CAPITULO|SECCION|SUBSECCION)\s+(PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|UNICO|PRELIMINAR|[IVXL]+) ')
    for a in articulos_parseados:
        assert not regex.search(a.texto), f"El articulo {a.numero} tiene contaminacion de jerarquia en su texto."

def test_nombre_multilinea_libro_ii(articulos_parseados):
    art_74 = next(a for a in articulos_parseados if a.numero == 74)
    assert art_74.libro.endswith("AJENA"), f"El libro del art 74 no unio la segunda linea: {art_74.libro}"

def test_nombre_multilinea_capitulo_i_sucesiones(articulos_parseados):
    art_1000 = next(a for a in articulos_parseados if a.numero == 1000)
    assert art_1000.capitulo.endswith("HERENCIA"), f"El capitulo del art 1000 no unio la segunda linea: {art_1000.capitulo}"
