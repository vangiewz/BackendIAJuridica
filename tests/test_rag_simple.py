from uuid import uuid4
from types import SimpleNamespace

from app.models.ia.esquemas import FuenteIA, RespuestaSimpleModelo
from app.services.ia.rag_simple import (generar_simple, _depurar_referencias,
    _quitar_andamiaje)
from app.services.conocimiento.expansion_consulta import expandir_consulta
from app.services.conocimiento.busqueda_hibrida import afinidad_tematica


def fuente(numero=711, texto="Si el arrendador enajena la cosa, el adquirente debe respetar el arrendamiento en curso."):
    return FuenteIA(id=uuid4(), codigo="Código Civil", numero_articulo=numero,
        articulo=f"Artículo {numero}", epigrafe="Enajenación de la cosa", texto=texto,
        version=1, estado_vigencia="sin_verificar", fuente_nombre="fixture",
        fuente_url="", contenido_hash="fixture")


class ClienteFalso:
    settings = SimpleNamespace(ollama_model="qwen3:8b")
    last_metrics = {"prompt_eval_count": 400, "eval_count": 120}

    def __init__(self, respuesta):
        self.respuesta = respuesta
        self.llamadas = 0

    def generar(self, mensajes, esquema, intentos):
        self.llamadas += 1
        assert esquema is RespuestaSimpleModelo
        assert intentos == 1
        assert "F1C1" in mensajes[1]["content"]
        return self.respuesta


def test_una_generacion_con_cita_literal_y_respuesta_natural():
    norma = fuente()
    cliente = ClienteFalso(RespuestaSimpleModelo(
        respuesta="Con lo que contás, habría que revisar la fecha cierta del contrato. El artículo 711 condiciona el efecto de la venta.",
        citas=["F1C1"]))
    resultado = generar_simple("Alquilo un inmueble y lo quieren vender", [norma], client=cliente)
    assert cliente.llamadas == 1
    assert resultado.estado == "fundamentada"
    assert resultado.conclusion.startswith("Con lo que contás")
    assert resultado.analisis[0].cita_textual == norma.texto
    assert resultado.analisis[0].norma_id == norma.id


def test_referencia_inventada_y_cita_invalida_se_descartan_sin_retry():
    norma = fuente()
    cliente = ClienteFalso(RespuestaSimpleModelo(
        respuesta="El artículo 9999 obliga al propietario. El artículo 711 requiere examinar el contrato.",
        citas=["F9C1", "F1C1"]))
    resultado = generar_simple("Consulta de alquiler", [norma], client=cliente)
    assert cliente.llamadas == 1
    assert resultado.estado == "fundamentada"
    assert "9999" not in resultado.conclusion
    assert resultado.trazabilidad["referencias_descartadas"] == 1
    assert resultado.trazabilidad["citas_invalidas_descartadas"] == 1


def test_no_rechaza_cifras_del_relato_ni_constitucion_generica():
    texto, descartadas = _depurar_referencias(
        "El 05/05/2026 recibí el aviso. Conviene revisar la constitución de la garantía.",
        [fuente()])
    assert descartadas == 0
    assert "05/05/2026" in texto


def test_alquiler_venta_prioriza_enajenacion_sobre_cobro():
    consulta = ("Firme un contrato de alquiler por un ano y el propietario me pidio "
                "que desocupe el inmueble porque quiere venderlo")
    expandida, conceptos = expandir_consulta(consulta)
    # La consulta original no se pierde y el tema no se desvia hacia el cobro del canon.
    assert "alquiler" in expandida and "venderlo" in expandida
    assert "enajenacion" in expandida and "extincion" in expandida
    assert "canon" not in expandida
    enajenacion = SimpleNamespace(epigrafe="Enajenacion de la cosa arrendada",
                                  texto="El arrendamiento en curso se respeta.")
    cobro = SimpleNamespace(epigrafe="Creditos del arrendador",
                            texto="Pago de canones del arrendamiento.")
    ajeno = SimpleNamespace(epigrafe="Carga de la prueba",
                            texto="Quien pretende un derecho debe probar los hechos.")
    assert afinidad_tematica(conceptos, enajenacion) > afinidad_tematica(conceptos, cobro)
    assert afinidad_tematica(conceptos, cobro) > afinidad_tematica(conceptos, ajeno)


def test_sin_conceptos_la_consulta_pasa_intacta_y_no_hay_reordenamiento():
    consulta = "Que diferencia existe entre mora e incumplimiento de una obligacion"
    expandida, conceptos = expandir_consulta(consulta)
    assert expandida == consulta and conceptos == []
    assert afinidad_tematica(conceptos, SimpleNamespace(epigrafe="Mora", texto="x")) == 0


def test_respuesta_larga_conserva_parrafos_y_sobrevive_sin_citas_validas():
    norma = fuente()
    salto = chr(10) * 2
    larga = salto.join(["TU SITUACION", "Firmaste un contrato por un ano.",
                        "ANALISIS", "El articulo 711 exige revisar la fecha cierta.",
                        "CONCLUSION", "Habria que revisar el contrato."])
    cliente = ClienteFalso(RespuestaSimpleModelo(respuesta=larga, citas=["F7C3"]))
    resultado = generar_simple("Consulta de alquiler", [norma], client=cliente)
    assert cliente.llamadas == 1
    assert resultado.estado == "fundamentada"
    assert resultado.conclusion == larga
    assert resultado.conclusion.count(salto) == 5
    assert resultado.fuentes == [norma]
    assert resultado.trazabilidad["citas_invalidas_descartadas"] == 1


def test_identificadores_internos_no_llegan_al_usuario():
    salto = chr(10)
    real = salto.join(["Podes revisar el contrato.", "", "**Citas**", "F1C1, F4C1, F727C2"])
    assert _quitar_andamiaje(real) == "Podes revisar el contrato."
    assert _quitar_andamiaje("El arrendamiento se respeta (F1C2) hoy.") == (
        "El arrendamiento se respeta hoy.")
    intacto = salto.join(["Parrafo uno.", "", "Parrafo dos."])
    assert _quitar_andamiaje(intacto) == intacto
