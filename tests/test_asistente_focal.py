from types import SimpleNamespace

from app.models.ia.esquemas import RespuestaDocumentoModelo
from app.services.conocimiento.expansion_consulta import expandir_consulta
from app.services.conocimiento.busqueda_hibrida import pertinencia_suficiente
from app.services.ia.consulta_documento import responder_documento
from app.services.ia.documento_rag import recuperar
from app.services.ia.rag import es_relato_de_hechos


DOCUMENTO = """CONTRATO DE PRESTAMO
PRIMERA. PARTES
Ana, prestamista, y Luis, prestatario, comparecen.
SEGUNDA. PLAZO
El plazo de devolucion comienza el 15 de marzo de 2026 y la fecha final de pago es el 15 de marzo de 2027.
TERCERA. FIRMAS
Ana y Luis firman el documento. El garante Pedro suscribe sin numero de identidad.
"""


def test_expansion_y_pertinencia_de_responsabilidad_contractual():
    pregunta = "¿Qué establece el Código Civil sobre responsabilidad contractual?"
    texto, conceptos = expandir_consulta(pregunta)
    assert "responsabilidad contractual" in texto
    assert "incumplimiento" in texto and "resarcimiento" in texto
    assert conceptos
    lateral = SimpleNamespace(epigrafe="Responsabilidad del vendedor",
        texto="El vendedor responde por eviccion de la cosa.")
    directo = SimpleNamespace(epigrafe="Responsabilidad del deudor",
        texto="El deudor que no cumple debe resarcir el dano por incumplimiento.")
    assert not pertinencia_suficiente(pregunta, lateral)
    assert pertinencia_suficiente(pregunta, directo)
    assert not es_relato_de_hechos(pregunta)
    assert es_relato_de_hechos("Mi inquilino no paga el alquiler")
    assert not es_relato_de_hechos("¿Qué pasa si mi inquilino no paga?")


def test_documento_corto_completo_prioriza_la_clausula_directa():
    assert recuperar(DOCUMENTO, "¿Quiénes son las partes?")[0].etiqueta.endswith("PRIMERA")
    for pregunta in ("¿Cuál es el plazo?", "¿Cuándo empieza?", "¿Y cuándo termina?"):
        fragmentos = recuperar(DOCUMENTO, pregunta)
        assert len(fragmentos) == 3
        assert fragmentos[0].etiqueta.endswith("SEGUNDA")


class ClienteSimulado:
    last_metrics = {}

    def __init__(self, respuesta, encontrado=True):
        self.respuesta = respuesta
        self.encontrado = encontrado

    def generar(self, mensajes, esquema, intentos=2):
        assert esquema is RespuestaDocumentoModelo
        return esquema(respuesta=self.respuesta, fragmentos_usados=["D1"],
                       encontrado=self.encontrado)


def test_no_amplia_el_inicio_del_plazo_al_contrato():
    respuesta = responder_documento("¿Cuándo empieza?", DOCUMENTO, "contrato.pdf",
        client=ClienteSimulado("El contrato empieza el 15 de marzo de 2026."))
    assert respuesta.estado == "fundamentada"
    assert "plazo de devolucion comienza" in respuesta.conclusion
    assert "contrato empieza" not in respuesta.conclusion
    assert respuesta.fuentes_documento[0].etiqueta.endswith("SEGUNDA")


def test_no_amplia_fecha_final_de_pago_al_prestamo():
    respuesta = responder_documento("¿Y cuándo termina?", DOCUMENTO, "contrato.pdf",
        client=ClienteSimulado("El prestamo termina el 15 de marzo de 2027."))
    assert respuesta.estado == "fundamentada"
    assert "fecha final de pago" in respuesta.conclusion
    assert "prestamo termina" not in respuesta.conclusion


def test_dato_ausente_se_abstiene():
    respuesta = responder_documento("¿Cuál es el CI del garante?", DOCUMENTO,
        "contrato.pdf", client=ClienteSimulado("", encontrado=False))
    assert respuesta.estado == "insuficiente"
    assert respuesta.fuentes_documento == []
