import pytest
from app.services.documentos.extractor_entidades import extraer

# Documento sintetico para pruebas offline
DOC_COMPLETO = """CONTRATO DE COMPRAVENTA

Conste por el presente contrato que suscriben Juan con C.I. 1234567 L.P. 
y Pedro con C.I. 8765432. NIT 1234567890.

CLAUSULA PRIMERA.- (OBJETO)
El 15/03/2024 se firma el acuerdo por Bs 1,500.00.

CLAUSULA SEGUNDA.- (PRECIO)
El precio es Bs. 1.500,00, que equivale a $us. 200.
El 15 de marzo de 2024 se debe pagar, o a más tardar el 15 de marzianos de 2024.

TERCERA.- (PLAZO)
El plazo es de 30 dias y dura 2 años."""

def test_extraer_entidades_varias():
    extraccion = extraer(DOC_COMPLETO)
    h = extraccion.hallazgos
    
    # Comprobar hallazgos ordenados
    assert all(h[i].inicio < h[i+1].inicio for i in range(len(h)-1))
    
    # Bs 1,500.00 (monto_bs conserva formato)
    bs_formato_us = next(x for x in h if x.texto == "Bs 1,500.00")
    assert bs_formato_us.tipo == "monto_bs"
    assert bs_formato_us.clausula == 1
    assert DOC_COMPLETO[bs_formato_us.inicio:bs_formato_us.fin] == bs_formato_us.texto
    
    # Bs. 1.500,00
    bs_formato_bo = next(x for x in h if x.texto == "Bs. 1.500,00")
    assert bs_formato_bo.tipo == "monto_bs"
    assert bs_formato_bo.clausula == 2
    
    # $us. 200
    us = next(x for x in h if x.texto == "$us. 200")
    assert us.tipo == "monto_usd"
    assert us.clausula == 2
    
    # C.I. 1234567 L.P.
    ci_lp = next(x for x in h if x.texto == "C.I. 1234567 L.P.")
    assert ci_lp.tipo == "cedula"
    assert ci_lp.clausula is None  # En el preambulo
    
    # C.I. 8765432
    ci_solo = next(x for x in h if x.texto == "C.I. 8765432")
    assert ci_solo.tipo == "cedula"
    assert ci_solo.clausula is None
    
    # FECHAS
    f_num = next(x for x in h if x.texto == "15/03/2024")
    assert f_num.tipo == "fecha"
    
    f_larga = next(x for x in h if x.texto == "15 de marzo de 2024")
    assert f_larga.tipo == "fecha"
    
    # "15 de marzianos" NO deberia estar
    assert not any("marzianos" in x.texto for x in h)
    
    # PARRAFO PARTES
    assert extraccion.parrafo_partes is not None
    assert "Conste por el presente" in extraccion.parrafo_partes
    assert "NIT 1234567890" in extraccion.parrafo_partes
    assert "CLAUSULA PRIMERA" not in extraccion.parrafo_partes

def test_parrafo_partes_sin_encabezado():
    # Documento sintetico
    texto = "Conste por el presente que yo, Juan, debo dinero a Pedro.\n\nFin del documento."
    extraccion = extraer(texto)
    assert extraccion.parrafo_partes == "Conste por el presente que yo, Juan, debo dinero a Pedro."

def test_sin_formula_apertura():
    # Documento sintetico
    texto = "Un documento sin formula.\nCLAUSULA PRIMERA.- Algo"
    extraccion = extraer(texto)
    assert extraccion.parrafo_partes is None

def test_entre_suelto_no_dispara_el_parrafo_de_partes():
    """La palabra "entre" aparece en cualquier parrafo y ganaba por llegar primero."""
    # Documento sintetico
    texto = (
        "Este acuerdo, entre otras cosas, regula lo siguiente.\n\n"
        "Conste por el presente que suscriben Pedro y Ana."
    )
    extraccion = extraer(texto)
    assert extraccion.parrafo_partes == "Conste por el presente que suscriben Pedro y Ana."
