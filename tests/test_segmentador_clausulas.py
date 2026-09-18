import pytest
from app.services.documentos.segmentador_clausulas import segmentar

# Documento sintetico para pruebas offline
DOC_SINTETICO_1 = """CONTRATO DE COMPRAVENTA

Conste por el presente contrato que suscriben Juan y Pedro.

CLAUSULA PRIMERA.- (OBJETO)
El vendedor da en venta el inmueble.

CLAUSULA SEGUNDA.- (PRECIO)
El precio es Bs. 1.500,00.

TERCERA.- (PLAZO)
El plazo es de 30 dias.

CUARTA.- (GASTOS)
Los gastos corren por el comprador.

ARTICULO 5
Penalidades."""

def test_segmentar_encuentra_clausulas():
    clausulas = segmentar(DOC_SINTETICO_1)
    
    assert len(clausulas) == 5
    assert clausulas[0].orden == 1
    assert clausulas[0].ordinal == "PRIMERA"
    assert clausulas[0].encabezado == "CLAUSULA PRIMERA.- (OBJETO)"
    assert "El vendedor da en venta el inmueble." in clausulas[0].texto
    
    assert clausulas[1].orden == 2
    assert clausulas[1].ordinal == "SEGUNDA"
    
    assert clausulas[2].orden == 3
    assert clausulas[2].ordinal == "TERCERA"
    assert clausulas[2].encabezado == "TERCERA.- (PLAZO)"
    
    assert clausulas[3].orden == 4
    assert clausulas[3].ordinal == "CUARTA"
    assert clausulas[3].encabezado == "CUARTA.- (GASTOS)"
    
    assert clausulas[4].orden == 5
    assert clausulas[4].ordinal == "5"
    assert clausulas[4].encabezado == "ARTICULO 5"

def test_segmentar_sin_clausulas():
    # Documento sintetico
    texto = "Un recibo simple de alquiler.\nBs. 1.500,00 recibidos."
    clausulas = segmentar(texto)
    assert clausulas == []

def test_segmentar_salto_ordinal():
    # Documento sintetico con salto
    texto = "CLAUSULA PRIMERA.-\nUno.\nCLAUSULA TERCERA.-\nTres."
    clausulas = segmentar(texto)
    assert len(clausulas) == 2
    assert clausulas[0].orden == 1
    assert clausulas[0].ordinal == "PRIMERA"
    assert clausulas[1].orden == 2
    assert clausulas[1].ordinal == "TERCERA"

def test_encabezado_conserva_mayusculas():
    texto = "cláusula segunda.-\nTexto"
    clausulas = segmentar(texto)
    assert clausulas[0].encabezado == "cláusula segunda.-"
    assert clausulas[0].ordinal == "SEGUNDA"
