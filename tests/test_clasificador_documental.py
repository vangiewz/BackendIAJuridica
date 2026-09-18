import pytest
from app.models.shared.enums import TipoDocumento
from app.services.documentos.clasificador_documental import clasificar_documento

def test_clasificacion_compraventa():
    # Sintético
    texto = "Este documento es una minuta de transferencia donde el vendedor acuerda con el comprador un precio de venta para el bien inmueble con matricula 12345."
    res = clasificar_documento(texto)
    assert res.tipo == TipoDocumento.COMPRAVENTA
    assert len(res.terminos_detectados) > 0

def test_clasificacion_arrendamiento():
    # Sintético
    texto = "Contrato de arrendamiento donde el arrendador entrega el inmueble arrendado al arrendatario por un canon mensual y un deposito en garantia."
    res = clasificar_documento(texto)
    assert res.tipo == TipoDocumento.ARRENDAMIENTO
    assert "arrendamiento" in res.terminos_detectados

def test_clasificacion_prestamo():
    # Sintético
    texto = "Contrato de mutuo donde el prestamista entrega al prestatario un capital prestado con una tasa de interes a un plazo de devolucion acordado."
    res = clasificar_documento(texto)
    assert res.tipo == TipoDocumento.PRESTAMO
    assert "mutuo" in res.terminos_detectados

def test_clasificacion_otro_receta():
    # Sintético
    texto = "Para hacer una torta de chocolate, mezclar harina, azucar, huevos y cacao. Hornear por 40 minutos a 180 grados."
    res = clasificar_documento(texto)
    assert res.tipo == TipoDocumento.OTRO
    assert len(res.terminos_detectados) == 0

def test_repeticion_no_suma_puntaje():
    # Sintético: repite 'arrendatario' muchas veces, sumaria 2.0 en total (1 sola vez)
    texto_arrendatario = "arrendatario " * 20
    
    # Otro documento con 3 terminos de compraventa distintos (suma 6.0)
    texto_compraventa = "comprador vendedor compraventa"
    
    res_arr = clasificar_documento(texto_arrendatario)
    res_comp = clasificar_documento(texto_compraventa)
    
    # Como el umbral es 3.0, el de arrendatario debería clasificar como OTRO (porque solo sumó 2.0)
    assert res_arr.tipo == TipoDocumento.OTRO
    assert res_comp.tipo == TipoDocumento.COMPRAVENTA

def test_puntajes_por_tipo_completo():
    texto = "acuerdo transaccional"
    res = clasificar_documento(texto)
    
    # Debe tener 5 tipos
    assert len(res.puntajes_por_tipo) == 5
    for tipo in TipoDocumento:
        assert tipo.value in res.puntajes_por_tipo
