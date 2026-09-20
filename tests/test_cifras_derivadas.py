"""Cifras derivadas: el porcentaje de un monto del caso se admite; nada más.

Una cifra puede ser literal (del relato o las fuentes), inventada, o el resultado de una
operación que el backend puede rehacer. Solo se admite una operación —porcentaje de un
monto—, con ambos operandos escritos en el caso. Estas pruebas fijan tanto lo que pasa
como lo que sigue rechazado, porque una lista de "permitidos" sin su contracara acaba
dejando pasar cualquier número.
"""
from types import SimpleNamespace

import pytest

from app.models.ia.esquemas import RespuestaCasoComplejo, RevisionModelo
from app.services.ia import rag
from app.services.ia.ollama_client import IAError, RespuestaInvalida
from app.services.ia.casos import ProblemaDetectado
from app.services.ia.validacion import cifras_derivadas, validar_caso_complejo, verificar_prosa

FUENTE = SimpleNamespace(numero_articulo=948, codigo="Codigo Civil", id="f1",
                         texto="La pena convencional no puede exceder de la obligacion principal.")
RELATO = ("Contrate una remodelacion por Bs 120.000. La clausula penal es del 0,5% diario, "
          "con un tope del 10% del valor del contrato. Pague Bs 92.000 y quedan Bs 28.000.")


def prosa(texto, datos=RELATO, derivadas=True):
    verificar_prosa(texto, [FUENTE], datos, permitir_derivadas=derivadas)


# --- lo que se admite -------------------------------------------------------------

def test_el_diez_por_ciento_de_120000_es_12000():
    prosa("El tope del 10% es de Bs 12.000.")


def test_el_mismo_calculo_sobre_otro_monto():
    datos = "El contrato es por Bs 180.000, con una clausula penal con tope del 10%."
    prosa("El tope alcanza Bs 18.000.", datos)


def test_la_tipografia_del_resultado_no_importa():
    prosa("El tope es de Bs 12000.")
    prosa("El tope es de Bs 12.000,00.")


def test_un_porcentaje_menor_de_un_monto_con_decimales():
    # 0,5% de 120.000 = 600: la penalidad de un dia.
    prosa("Cada dia de retraso equivale a Bs 600.")


def test_el_porcentaje_se_aplica_a_cualquier_monto_del_caso():
    # 10% de 28.000 = 2.800: el saldo tambien es un monto del relato.
    prosa("El diez por ciento del saldo seria de Bs 2.800.")


# --- lo que sigue rechazado -------------------------------------------------------

def test_un_resultado_que_no_coincide_se_rechaza():
    with pytest.raises(RespuestaInvalida) as error:
        prosa("El tope del 10% es de Bs 13.000.")
    assert error.value.motivo == "cifra_fuera_de_fuentes"
    assert error.value.detalle == "13.000"


def test_una_cifra_sin_relacion_matematica_se_rechaza():
    with pytest.raises(RespuestaInvalida):
        prosa("La indemnizacion seria de Bs 45.700.")


def test_una_operacion_distinta_al_porcentaje_no_se_admite():
    # 77 dias x 600 = 46.200 y 120.000 - 92.000 = 28.000: esta ultima ya consta, pero la
    # multiplicacion por dias es otra operacion y no se acepta.
    with pytest.raises(RespuestaInvalida):
        prosa("Por 77 dias de retraso corresponden Bs 46.200.")


def test_sin_un_porcentaje_en_el_caso_no_hay_nada_que_derivar():
    datos = "Contrate una remodelacion por Bs 120.000 y pague Bs 92.000."
    with pytest.raises(RespuestaInvalida):
        prosa("El tope seria de Bs 12.000.", datos)


def test_sin_un_monto_en_el_caso_no_hay_nada_que_derivar():
    # "10%" solo, sin importe: no hay sobre que calcular.
    with pytest.raises(RespuestaInvalida):
        prosa("El tope es de Bs 12.000.", "La clausula penal tiene un tope del 10%.")


def test_los_resultados_admisibles_son_pocos_y_exactos():
    derivadas = cifras_derivadas(RELATO.lower())
    # 3 montos (120.000, 92.000, 28.000) x 2 porcentajes (0,5 y 10) = 6 resultados.
    assert len(derivadas) == 6
    assert all(valor > 0 for valor in derivadas)


# --- el resto de los validadores no cambia ----------------------------------------

def test_por_defecto_la_derivacion_esta_apagada():
    # Contratos redactados y analizados no pueden mostrar un importe que el usuario no
    # dio, aunque este bien calculado: el flag solo lo enciende el analisis juridico.
    with pytest.raises(RespuestaInvalida):
        prosa("El tope es de Bs 12.000.", derivadas=False)


def test_un_articulo_inexistente_sigue_rechazado_con_derivacion_encendida():
    with pytest.raises(RespuestaInvalida) as error:
        prosa("Segun el articulo 9999 el tope es de Bs 12.000.")
    assert error.value.motivo == "articulo_fuera_de_fuentes"


def test_una_cifra_derivada_no_habilita_normas_externas():
    with pytest.raises(RespuestaInvalida):
        prosa("El tope de Bs 12.000 surge de la Constitucion.")


def test_el_caso_complejo_admite_la_cifra_derivada_en_una_explicacion():
    items = [{"fuente": "F1", "cita": "no puede exceder", "problema": "p1", "apartado": 0,
              "explicacion": "El tope del 10% equivale a Bs 12.000."}]
    validar_caso_complejo(items, "Resumen del caso.", "Conclusion orientativa.", [],
                          [FUENTE], RELATO)


def test_el_caso_complejo_rechaza_una_cifra_inventada():
    items = [{"fuente": "F1", "cita": "no puede exceder", "problema": "p1", "apartado": 0,
              "explicacion": "El tope equivale a Bs 13.000."}]
    with pytest.raises(RespuestaInvalida):
        validar_caso_complejo(items, "Resumen.", "Conclusion.", [], [FUENTE], RELATO)


# --- la revision de coherencia ----------------------------------------------------

class RevisorFalso:
    def __init__(self, revision=None, falla=False):
        self.revision, self.falla, self.mensajes = revision, falla, None

    def generar(self, mensajes, schema, intentos=2):
        assert schema is RevisionModelo
        self.mensajes = mensajes
        if self.falla:
            raise IAError("sin servicio")
        return self.revision


def caso():
    problemas = [ProblemaDetectado("p1", "Clausula penal", "clausula penal"),
                 ProblemaDetectado("p2", "Vicios de la obra", "vicios obra")]
    generado = RespuestaCasoComplejo.model_validate({
        "analisis": [{"pregunta_id": "q1", "problema": "p1", "estado": "fundamentado",
                      "hechos_usados": [], "citas": ["F1C1"],
                      "regla": "X" * 450, "aplicacion": "X" * 450, "conclusion": "X" * 100}],
        "limitaciones": ["No se conoce si existe clausula penal.", "Falta el peritaje."]})
    return problemas, generado


def test_la_revision_quita_las_limitaciones_que_marca_y_conserva_el_resto():
    problemas, generado = caso()
    revisor = RevisorFalso(RevisionModelo(limitaciones_irrelevantes=[0], coherente=False))
    traza = {}
    limitaciones, omitidos = rag._revisar(RELATO, problemas, generado,
                                          list(generado.limitaciones), revisor, traza)
    assert limitaciones == ["Falta el peritaje."]
    assert omitidos == []
    assert traza["revision_coherente"] is False
    assert traza["limitaciones_descartadas_revision"] == 1


def test_la_revision_ignora_indices_fuera_de_rango():
    problemas, generado = caso()
    revisor = RevisorFalso(RevisionModelo(limitaciones_irrelevantes=[7, -1], coherente=True))
    limitaciones, _ = rag._revisar(RELATO, problemas, generado, list(generado.limitaciones),
                                   revisor, {})
    assert limitaciones == generado.limitaciones


def test_la_revision_traduce_el_id_del_problema_a_su_titulo():
    problemas, generado = caso()
    titulos = {"p1": "Clausula penal", "p2": "Vicios de la obra"}
    revisor = RevisorFalso(RevisionModelo(problemas_omitidos=["Vicios de la obra"],
                                          coherente=False))
    _, omitidos = rag._revisar(RELATO, problemas, generado, [], revisor, {}, titulos)
    # El revisor ve titulos en PROBLEMAS y en APARTADOS, no ids sueltos.
    import json
    cuerpo = json.loads(revisor.mensajes[1]["content"])
    assert cuerpo["PROBLEMAS"] == ["Clausula penal", "Vicios de la obra"]
    assert cuerpo["APARTADOS"][0]["problema"] == "Clausula penal"
    assert omitidos == ["Vicios de la obra"]


def test_un_problema_que_si_se_trato_no_se_reporta_como_omitido():
    problemas, generado = caso()
    titulos = {"p1": "Clausula penal", "p2": "Vicios de la obra"}
    revisor = RevisorFalso(RevisionModelo(problemas_omitidos=["Clausula penal"],
                                          coherente=True))
    _, omitidos = rag._revisar(RELATO, problemas, generado, [], revisor, {}, titulos)
    assert omitidos == []


def test_la_revision_recibe_un_extracto_y_no_el_apartado_completo():
    # 900 caracteres de explicacion: en el prompt del revisor entran solo los primeros.
    problemas, generado = caso()
    revisor = RevisorFalso(RevisionModelo(coherente=True))
    rag._revisar(RELATO, problemas, generado, [], revisor, {})
    import json
    extracto = json.loads(revisor.mensajes[1]["content"])["APARTADOS"][0]["extracto"]
    assert len(extracto) == rag.EXTRACTO_REVISION < 900


def test_si_la_revision_falla_la_respuesta_se_conserva_sin_cambios():
    problemas, generado = caso()
    traza = {}
    limitaciones, omitidos = rag._revisar(RELATO, problemas, generado,
                                          list(generado.limitaciones),
                                          RevisorFalso(falla=True), traza)
    assert limitaciones == generado.limitaciones and omitidos == []
    assert traza["revision"] == "no_disponible"
