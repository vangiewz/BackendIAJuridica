from app.services.documentos.comparador import (
    comparar, TIPO_AGREGADO, TIPO_ELIMINADO, TIPO_MODIFICADO,
    ESTRATEGIA_CLAUSULAS, ESTRATEGIA_TEXTO,
)

BASE = """CONTRATO DE COMPRAVENTA

CLAUSULA PRIMERA.- El VENDEDOR es propietario del lote ubicado en la zona Norte.

CLAUSULA SEGUNDA.- El precio convenido es de Bs. 100.000.- pagaderos al contado.

CLAUSULA TERCERA.- La entrega se realizara en el plazo de 12 meses.
"""


def _de_tipo(diferencias, tipo):
    return [d for d in diferencias if d.tipo == tipo]


def test_documentos_identicos_no_tienen_diferencias():
    resultado = comparar(BASE, BASE)
    assert resultado.diferencias == ()


def test_detecta_monto_modificado_y_lo_explica():
    modificado = BASE.replace("Bs. 100.000", "Bs. 120.000")
    resultado = comparar(BASE, modificado)

    assert resultado.estrategia == ESTRATEGIA_CLAUSULAS
    assert len(resultado.diferencias) == 1

    diferencia = resultado.diferencias[0]
    assert diferencia.tipo == TIPO_MODIFICADO
    assert diferencia.ubicacion == "Cláusula SEGUNDA"
    assert diferencia.clausula == 2
    assert "Bs. 100.000" in (diferencia.texto_anterior or "")
    assert "Bs. 120.000" in (diferencia.texto_nuevo or "")
    # La explicacion nombra el dato que cambio, no una consecuencia juridica.
    assert diferencia.explicacion == "El monto cambió de Bs. 100.000 a Bs. 120.000."


def test_detecta_plazo_modificado():
    modificado = BASE.replace("12 meses", "24 meses")
    diferencias = comparar(BASE, modificado).diferencias

    assert len(diferencias) == 1
    assert diferencias[0].explicacion == "El plazo cambió de 12 meses a 24 meses."


def test_modificacion_sin_dato_reconocible_usa_explicacion_neutral():
    modificado = BASE.replace("zona Norte", "zona Sur")
    diferencias = comparar(BASE, modificado).diferencias

    assert len(diferencias) == 1
    assert diferencias[0].explicacion == "El contenido de esta sección fue modificado."


def test_detecta_clausula_agregada():
    agregada = BASE + "\nCLAUSULA CUARTA.- Las partes se someten a la via civil.\n"
    diferencias = comparar(BASE, agregada).diferencias

    agregados = _de_tipo(diferencias, TIPO_AGREGADO)
    assert len(agregados) == 1
    assert agregados[0].ubicacion == "Cláusula CUARTA"
    assert agregados[0].texto_anterior is None
    assert "via civil" in (agregados[0].texto_nuevo or "")
    assert agregados[0].explicacion == "Se agregó la cláusula cuarta."


def test_detecta_clausula_eliminada():
    # El documento nuevo es el original sin la tercera clausula.
    sin_tercera = BASE.split("CLAUSULA TERCERA")[0]
    diferencias = comparar(BASE, sin_tercera).diferencias

    eliminados = _de_tipo(diferencias, TIPO_ELIMINADO)
    assert len(eliminados) == 1
    assert eliminados[0].ubicacion == "Cláusula TERCERA"
    assert eliminados[0].texto_nuevo is None
    assert eliminados[0].explicacion == "Se eliminó la cláusula tercera."


def test_sin_clausulas_cae_a_comparacion_por_parrafos():
    a = "Primer parrafo del acuerdo entre las partes.\n\nSegundo parrafo con el monto de Bs. 500.\n"
    b = "Primer parrafo del acuerdo entre las partes.\n\nSegundo parrafo con el monto de Bs. 900.\n"

    resultado = comparar(a, b)

    assert resultado.estrategia == ESTRATEGIA_TEXTO
    assert len(resultado.diferencias) == 1
    diferencia = resultado.diferencias[0]
    assert diferencia.tipo == TIPO_MODIFICADO
    assert diferencia.ubicacion == "Párrafo 2"
    assert diferencia.clausula is None
    assert diferencia.explicacion == "El monto cambió de Bs. 500 a Bs. 900."


def test_parrafo_agregado_y_eliminado_sin_clausulas():
    a = "Parrafo que se mantiene.\n\nParrafo que desaparece.\n"
    b = "Parrafo que se mantiene.\n\nParrafo nuevo del final.\n\nOtro parrafo nuevo.\n"

    diferencias = comparar(a, b).diferencias

    assert len(_de_tipo(diferencias, TIPO_MODIFICADO)) == 1
    assert len(_de_tipo(diferencias, TIPO_AGREGADO)) == 1


def test_el_espaciado_no_cuenta_como_cambio():
    con_otro_espaciado = BASE.replace("El precio convenido", "El   precio    convenido")
    assert comparar(BASE, con_otro_espaciado).diferencias == ()
