import pytest
from app.models.shared.enums import TipoDocumento, SeveridadRiesgo
from app.services.contratos.motor_riesgos import analizar
from app.services.contratos.catalogo_riesgos import Riesgo

# Contratos sinteticos para pruebas offline

def test_cv_precio_ausente():
    texto = """CONTRATO DE COMPRAVENTA
    CLAUSULA PRIMERA.- El vendedor transfiere la propiedad.
    CLAUSULA SEGUNDA.- El comprador acepta.
    Fecha: 2023-01-01. CI: 1234567."""
    analisis = analizar(texto, TipoDocumento.COMPRAVENTA)
    riesgos = {r.codigo for r in analisis.riesgos}
    assert 'CV-PRECIO-AUSENTE' in riesgos
    
    r = next(r for r in analisis.riesgos if r.codigo == 'CV-PRECIO-AUSENTE')
    assert 613 in r.articulos

def test_cv_precio_presente():
    texto = """CONTRATO DE COMPRAVENTA
    CLAUSULA PRIMERA.- El precio es de Bs. 150.000,00.
    Fecha: 2023-01-01. CI: 1234567."""
    analisis = analizar(texto, TipoDocumento.COMPRAVENTA)
    riesgos = {r.codigo for r in analisis.riesgos}
    assert 'CV-PRECIO-AUSENTE' not in riesgos

def test_ar_sin_plazo():
    texto = """CONTRATO DE ARRENDAMIENTO
    CLAUSULA PRIMERA.- Se da en arriendo.
    Fecha: 2023-01-01. CI: 1234567."""
    analisis = analizar(texto, TipoDocumento.ARRENDAMIENTO)
    riesgos = {r.codigo for r in analisis.riesgos}
    assert 'AR-SIN-PLAZO' in riesgos
    r = next(r for r in analisis.riesgos if r.codigo == 'AR-SIN-PLAZO')
    assert 687 in r.articulos

def test_ar_subarriendo_sin_autorizacion():
    texto = """CONTRATO DE ARRENDAMIENTO
    CLAUSULA PRIMERA.- El arrendatario podra subarrendar el inmueble a terceros.
    Plazo: 1 año. Fecha: 2023-01-01. CI: 1234567."""
    analisis = analizar(texto, TipoDocumento.ARRENDAMIENTO)
    riesgos = {r.codigo for r in analisis.riesgos}
    assert 'AR-SUBARRIENDO-SIN-AUTORIZACION' in riesgos
    r = next(r for r in analisis.riesgos if r.codigo == 'AR-SUBARRIENDO-SIN-AUTORIZACION')
    assert 707 in r.articulos

def test_ar_subarriendo_prohibido():
    texto = """CONTRATO DE ARRENDAMIENTO
    CLAUSULA PRIMERA.- Queda terminantemente prohibido subarrendar el inmueble.
    Plazo: 1 año. Fecha: 2023-01-01. CI: 1234567."""
    analisis = analizar(texto, TipoDocumento.ARRENDAMIENTO)
    riesgos = {r.codigo for r in analisis.riesgos}
    assert 'AR-SUBARRIENDO-SIN-AUTORIZACION' not in riesgos

def test_ar_anticretico_simultaneo():
    texto = """CONTRATO DE ARRENDAMIENTO
    CLAUSULA PRIMERA.- Se da en arriendo y anticretico el inmueble.
    Plazo: 1 año. Fecha: 2023-01-01. CI: 1234567."""
    analisis = analizar(texto, TipoDocumento.ARRENDAMIENTO)
    riesgos = {r.codigo for r in analisis.riesgos}
    assert 'AR-ANTICRETICO-SIMULTANEO' in riesgos
    r = next(r for r in analisis.riesgos if r.codigo == 'AR-ANTICRETICO-SIMULTANEO')
    assert 716 in r.articulos

def test_pr_interes_pactado():
    texto = """CONTRATO DE PRESTAMO
    CLAUSULA PRIMERA.- Se acuerda un interes del 5% mensual.
    Plazo: 1 año. Fecha: 2023-01-01. CI: 1234567."""
    analisis = analizar(texto, TipoDocumento.PRESTAMO)
    riesgos = {r.codigo for r in analisis.riesgos}
    assert 'PR-INTERES-PACTADO' in riesgos
    r = next(r for r in analisis.riesgos if r.codigo == 'PR-INTERES-PACTADO')
    assert 413 in r.articulos
    assert "no lo fija el Código Civil" in r.explicacion
    assert "usuraria" not in r.explicacion.lower()

def test_pr_interes_capitalizado():
    texto = """CONTRATO DE PRESTAMO
    CLAUSULA PRIMERA.- Los intereses no pagados seran capitalizados al monto principal.
    Plazo: 1 año. Fecha: 2023-01-01. CI: 1234567."""
    analisis = analizar(texto, TipoDocumento.PRESTAMO)
    riesgos = {r.codigo for r in analisis.riesgos}
    assert 'PR-INTERES-CAPITALIZADO' in riesgos

def test_gen_sin_cedula():
    texto = """CONTRATO CIVIL
    CLAUSULA PRIMERA.- Las partes acuerdan.
    Fecha: 2023-01-01."""
    analisis = analizar(texto, TipoDocumento.OTRO)
    riesgos = {r.codigo for r in analisis.riesgos}
    assert 'GEN-SIN-CEDULA' in riesgos
    r = next(r for r in analisis.riesgos if r.codigo == 'GEN-SIN-CEDULA')
    assert 549 in r.articulos

def test_gen_sin_clausulas():
    texto = """Este es un contrato informal entre Juan CI: 1234567 y Pedro CI: 7654321.
    Acuerdan vender la casa en Bs. 150.000,00 el 2023-01-01."""
    analisis = analizar(texto, TipoDocumento.COMPRAVENTA)
    riesgos = {r.codigo for r in analisis.riesgos}
    assert 'GEN-SIN-CLAUSULAS' in riesgos
    r = next(r for r in analisis.riesgos if r.codigo == 'GEN-SIN-CLAUSULAS')
    assert 'limitación del sistema' in r.explicacion.lower() or 'limitación' in r.explicacion.lower()

def test_articulos_no_vacios():
    # Verificamos que todas las reglas devuelven Riesgo con articulos
    from app.services.contratos.reglas_comunes import REGLAS_COMUNES
    from app.services.contratos.reglas_compraventa import REGLAS_COMPRAVENTA
    from app.services.contratos.reglas_arrendamiento import REGLAS_ARRENDAMIENTO
    from app.services.contratos.reglas_prestamo import REGLAS_PRESTAMO

    from app.models.shared.enums import TipoDocumento
    from app.services.documentos.segmentador_clausulas import segmentar
    from app.services.documentos.extractor_entidades import extraer
    from app.services.shared.normalizacion import normalizar
    from app.services.contratos.catalogo_riesgos import ContextoContrato

    todas_las_reglas = list(REGLAS_COMUNES) + list(REGLAS_COMPRAVENTA) + list(REGLAS_ARRENDAMIENTO) + list(REGLAS_PRESTAMO)
    
    # Creamos un contexto que dispare la mayor cantidad de riesgos
    texto = "cosa ajena venta de herencia subarriendo anticretico interes del 5% capitalizados"
    texto_norm = normalizar(texto)
    extraccion = extraer(texto)
    ctx = ContextoContrato(
        tipo=TipoDocumento.COMPRAVENTA,
        texto=texto,
        texto_normalizado=texto_norm,
        clausulas=extraccion.clausulas,
        hallazgos=extraccion.hallazgos
    )

    for regla in todas_las_reglas:
        riesgo = regla(ctx)
        if riesgo:
            assert len(riesgo.articulos) > 0

def test_evidencia_exacta():
    texto = """CONTRATO DE ARRENDAMIENTO
    CLAUSULA PRIMERA.- Se da en arriendo y anticrético el inmueble a Juan CI: 1234567.
    Fecha: 2023-01-01."""
    analisis = analizar(texto, TipoDocumento.ARRENDAMIENTO)
    r = next((r for r in analisis.riesgos if r.evidencia is not None), None)
    if r:
        assert texto[r.inicio:r.inicio+len(r.evidencia)] == r.evidencia

def test_orden_riesgos():
    texto = """CONTRATO SIN NADA"""
    analisis = analizar(texto, TipoDocumento.COMPRAVENTA)
    # Deberia tener GEN-SIN-CEDULA (ALTA), CV-PRECIO-AUSENTE (ALTA), GEN-SIN-CLAUSULAS (MEDIA), GEN-SIN-FECHA (MEDIA)
    severidad_valores = {'alta': 0, 'media': 1, 'baja': 2}
    for i in range(len(analisis.riesgos) - 1):
        r1 = analisis.riesgos[i]
        r2 = analisis.riesgos[i+1]
        
        s1 = severidad_valores[r1.severidad.value]
        s2 = severidad_valores[r2.severidad.value]
        
        assert s1 <= s2
        if s1 == s2:
            idx1 = r1.inicio if r1.inicio is not None else float('inf')
            idx2 = r2.inicio if r2.inicio is not None else float('inf')
            assert idx1 <= idx2

def test_reglas_evaluadas_y_otro():
    # OTRO solo corre reglas comunes (3 reglas)
    analisis = analizar("texto", TipoDocumento.OTRO)
    assert analisis.reglas_evaluadas == 3
    
    analisis_cv = analizar("texto", TipoDocumento.COMPRAVENTA)
    assert analisis_cv.reglas_evaluadas == 6 # 3 comunes + 3 cv
