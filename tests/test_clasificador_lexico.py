import pytest
from app.models.shared.enums import AreaJuridica
from app.services.consultas.clasificador_lexico import clasificar, Clasificacion
from app.services.shared.normalizacion import normalizar

def test_clasificacion_contratos_terreno_transferencia():
    # "Compré un terreno, pagué todo, pero el vendedor no quiere hacer la transferencia" -> contratos
    texto = "Compré un terreno, pagué todo, pero el vendedor no quiere hacer la transferencia"
    resultado = clasificar(texto)
    assert resultado.area == AreaJuridica.CONTRATOS
    assert "compre" in resultado.terminos_detectados
    assert "terreno" in resultado.terminos_detectados

def test_clasificacion_sucesiones():
    # "Mi papá falleció y mis hermanos no me quieren dar mi parte" -> sucesiones
    texto = "Mi papá falleció y mis hermanos no me quieren dar mi parte"
    resultado = clasificar(texto)
    assert resultado.area == AreaJuridica.SUCESIONES
    assert "fallecio" in resultado.terminos_detectados or "papa fallecio" in resultado.terminos_detectados

def test_clasificacion_derechos_reales_muro():
    # "Mi vecino construyó un muro dentro de mi lote" -> derechos_reales
    texto = "Mi vecino construyó un muro dentro de mi lote"
    resultado = clasificar(texto)
    assert resultado.area == AreaJuridica.DERECHOS_REALES

def test_clasificacion_responsabilidad_civil():
    # "Me chocaron el auto y no quieren pagar los daños" -> responsabilidad_civil
    texto = "Me chocaron el auto y no quieren pagar los daños"
    resultado = clasificar(texto)
    assert resultado.area == AreaJuridica.RESPONSABILIDAD_CIVIL

def test_clasificacion_obligaciones_o_contratos():
    # "Le presté plata a un amigo y no me paga hace meses"
    texto = "Le presté plata a un amigo y no me paga hace meses"
    resultado = clasificar(texto)
    assert resultado.area in [AreaJuridica.OBLIGACIONES, AreaJuridica.CONTRATOS]

def test_clasificacion_saludo():
    # "hola, ¿cómo estás?" -> area=None, terminos_detectados vacio
    texto = "hola, ¿cómo estás?"
    resultado = clasificar(texto)
    assert resultado.area is None
    assert resultado.puntaje == 0.0
    assert len(resultado.terminos_detectados) == 0

def test_clasificacion_vacio():
    # "" -> area=None
    resultado = clasificar("")
    assert resultado.area is None
    assert resultado.puntaje == 0.0

def test_clasificacion_derechos_reales_usucapion():
    # "Necesito saber sobre la usucapión de un inmueble" -> derechos_reales
    texto = "Necesito saber sobre la usucapión de un inmueble"
    resultado = clasificar(texto)
    assert resultado.area == AreaJuridica.DERECHOS_REALES

def test_clasificacion_sucesiones_testamento():
    # "quiero hacer un testamento" -> sucesiones
    texto = "quiero hacer un testamento"
    resultado = clasificar(texto)
    assert resultado.area == AreaJuridica.SUCESIONES
    assert "testamento" in resultado.terminos_detectados

def test_coincidencia_por_palabra_completa():
    # "venta" clasifica como contratos; "ventana" no
    resultado_venta = clasificar("venta de casa")
    assert resultado_venta.area in [AreaJuridica.CONTRATOS, AreaJuridica.DERECHOS_REALES]
    
    resultado_ventana = clasificar("me rompieron la ventana")
    # No deberia detectar "venta"
    assert "venta" not in resultado_ventana.terminos_detectados

def test_insensibilidad_mayusculas_y_acentos():
    # "CONTRATO", "contrato" y "Contrató" dan el mismo resultado
    res1 = clasificar("CONTRATO")
    res2 = clasificar("contrato")
    res3 = clasificar("Contrató")
    
    assert res1.area == AreaJuridica.CONTRATOS
    assert res1.puntajes_por_area == res2.puntajes_por_area
    assert res2.puntajes_por_area == res3.puntajes_por_area

def test_orden_terminos_detectados():
    # terminos_detectados viene en el orden en que los terminos aparecen en la consulta
    texto = "hicimos un contrato y el vendedor me dio el terreno"
    resultado = clasificar(texto)
    assert resultado.area == AreaJuridica.CONTRATOS
    
    # "contrato", "vendedor", "terreno"
    idx_contrato = resultado.terminos_detectados.index("contrato")
    idx_vendedor = resultado.terminos_detectados.index("vendedor")
    idx_terreno = resultado.terminos_detectados.index("terreno")
    
    assert idx_contrato < idx_vendedor
    assert idx_vendedor < idx_terreno

def test_puntajes_por_area_incluye_cinco():
    # puntajes_por_area incluye siempre las cinco areas
    resultado = clasificar("accidente")
    assert len(resultado.puntajes_por_area) == 5
    for area in AreaJuridica:
        assert area.value in resultado.puntajes_por_area
