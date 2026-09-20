"""Controles de calidad del análisis complejo, sin llamadas al modelo."""
from pathlib import Path
from types import SimpleNamespace
import inspect

import pytest

from app.services.ia import rag
from app.services.ia.casos import (ProblemaDetectado, datos_estructurados,
                                   fuente_pertinente, problemas_de_preguntas)
from app.services.ia.ollama_client import RespuestaInvalida
from app.services.ia.validacion import validar_caso_complejo, verificar_prosa


RELATO = (Path(__file__).parent / "fixtures" / "caso_remodelacion.txt").read_text(encoding="utf-8")
DATOS = datos_estructurados(RELATO)
PREGUNTAS = problemas_de_preguntas(RELATO)
MORA = SimpleNamespace(id="mora", numero_articulo=340, codigo="Código Civil",
                       epigrafe="CONSTITUCIÓN EN MORA",
                       texto="El deudor queda constituido en mora mediante intimación o requerimiento judicial u otro acto equivalente del acreedor.")
VICIOS = SimpleNamespace(id="vicios", numero_articulo=741, codigo="Código Civil",
                        epigrafe="RESPONSABILIDAD POR VICIOS O POR FALTA DE CUALIDADES DE LA OBRA",
                        texto="El contratista responde por los vicios o por la falta de cualidades de la obra.")


def item(fuente="F1", problema="q1", explicacion="Con el relato aportado podría analizarse la mora."):
    literal = MORA.texto if fuente == "F1" else VICIOS.texto
    return {"fuente": fuente, "cita": literal[:35], "problema": problema,
            "apartado": 0, "explicacion": explicacion}


def validar(items, fuentes=None, mapa=None, problemas=None, apartados=None):
    return validar_caso_complejo(items, "Resumen del caso.", "Conclusión orientativa.", [],
                                 fuentes or [MORA, VICIOS], RELATO,
                                 por_problema=mapa if mapa is not None else {"q1": ["mora"], "q8": ["vicios"]},
                                 problemas=problemas or PREGUNTAS,
                                 datos_caso=DATOS, apartados=apartados)


def test_nueve_preguntas_conservadas_y_mora_presente():
    assert len(PREGUNTAS) == 9
    assert [p.clave for p in PREGUNTAS] == [f"q{i}" for i in range(1, 10)]
    assert PREGUNTAS[0].familia == "mora"
    assert "mora" in PREGUNTAS[0].pregunta


def test_mora_se_agrega_si_descomponedor_la_omite():
    class Modelo:
        def generar(self, *_args, **_kwargs):
            return SimpleNamespace(problemas=[SimpleNamespace(titulo="Vicios de la obra", consulta="vicios obra")])
    detectados = rag.descomponer_caso("La obra no se entregó al vencimiento y tiene defectos. " * 5,
                                      Modelo(), {})
    assert any(p.familia == "mora" for p in detectados)


def test_hechos_estructurados_conservan_papeles_y_fechas():
    assert {k: DATOS[k]["valor"] for k in ("precio_total", "anticipo", "saldo_pendiente", "gasto_adicional",
                                          "penalidad_diaria", "tope_contractual", "calculo_tope")} == {
        "precio_total": "180000", "anticipo": "72000", "saldo_pendiente": "108000",
        "gasto_adicional": "28000", "penalidad_diaria": "0.5", "tope_contractual": "10",
        "calculo_tope": "18000.00"}
    assert DATOS["fecha_entrega_pactada"]["valor"] == "30 de abril de 2026"
    assert DATOS["fecha_requerimiento"]["valor"] == "5 de mayo"


def test_fuente_de_otro_problema_rechazada():
    with pytest.raises(RespuestaInvalida) as exc:
        validar([item("F2", "q1")])
    assert exc.value.motivo == "fuente_de_otro_problema"


def test_cita_irrelevante_rechazada_aunque_fue_recuperada():
    with pytest.raises(RespuestaInvalida) as exc:
        validar([item("F2", "q1")], mapa={"q1": ["vicios"]})
    assert exc.value.motivo == "cita_irrelevante"


def test_no_se_acepta_mandato_ni_simulacion_para_obra():
    mandato = SimpleNamespace(epigrafe="RESPONSABILIDAD DEL MANDATARIO", texto="resarcimiento del daño")
    simulacion = SimpleNamespace(epigrafe="SIMULACIÓN DEL CONTRATO", texto="vicios de la obra")
    assert not fuente_pertinente(PREGUNTAS[4], mandato)
    assert not fuente_pertinente(PREGUNTAS[7], simulacion)


def test_saldo_108000_no_puede_ser_28000():
    with pytest.raises(RespuestaInvalida) as exc:
        verificar_prosa("El saldo pendiente es Bs 28.000.", [MORA], RELATO,
                        permitir_derivadas=True, datos_caso=DATOS)
    assert exc.value.motivo == "dato_contradicho"


def test_precio_anticipo_saldo_en_una_frase_correcta():
    verificar_prosa("Se pactó la obra por Bs 180.000, con anticipo de Bs 72.000 y saldo pendiente de Bs 108.000.",
                    [MORA], RELATO, permitir_derivadas=True, datos_caso=DATOS)


def test_penalidad_y_tope_en_una_frase_correcta():
    verificar_prosa("La cláusula penal del 0,5% por día tiene un máximo del 10%.",
                    [MORA], RELATO, permitir_derivadas=True, datos_caso=DATOS)


def test_penalidad_05_no_puede_ser_5():
    with pytest.raises(RespuestaInvalida) as exc:
        verificar_prosa("La penalidad es 5% por cada día.", [MORA], RELATO,
                        permitir_derivadas=True, datos_caso=DATOS)
    assert exc.value.motivo in {"dato_contradicho", "cifra_fuera_de_fuentes"}


def test_duracion_y_fecha_inventadas_rechazadas():
    for frase in ("Hubo 77 días de retraso.", "El requerimiento fue el 5 de abril de 2026."):
        with pytest.raises(RespuestaInvalida):
            verificar_prosa(frase, [MORA], RELATO, permitir_derivadas=True, datos_caso=DATOS)


def test_fecha_real_asignada_al_evento_equivocado_rechazada():
    with pytest.raises(RespuestaInvalida) as exc:
        verificar_prosa("El contratista abandonó la obra el 5 de mayo.", [MORA], RELATO,
                        permitir_derivadas=True, datos_caso=DATOS)
    assert exc.value.motivo == "fecha_con_evento_equivocado"


def test_calculo_verificado_admitido():
    verificar_prosa("El 10% de Bs 180.000 equivale a Bs 18.000.", [MORA], RELATO,
                    permitir_derivadas=True, datos_caso=DATOS)


def test_articulo_inexistente_rechazado():
    with pytest.raises(RespuestaInvalida) as exc:
        verificar_prosa("Según el artículo 9999, hay mora.", [MORA], RELATO,
                        permitir_derivadas=True, datos_caso=DATOS)
    assert exc.value.motivo == "articulo_fuera_de_fuentes"


def test_constitucion_en_mora_no_es_cita_a_constitucion():
    verificar_prosa("Debe analizarse la constitución en mora y lo que prevé la ley.",
                    [MORA], RELATO, permitir_derivadas=True, datos_caso=DATOS)
    with pytest.raises(RespuestaInvalida) as exc:
        verificar_prosa("Según la Constitución, hay mora.", [MORA], RELATO,
                        permitir_derivadas=True, datos_caso=DATOS)
    assert exc.value.motivo == "norma_externa_en_prosa"


@pytest.mark.parametrize("frase", (
    "Debe analizarse la constitución en mora del deudor.",
    "Puede discutirse la constitución de una garantía.",
    "La constitución de una obligación requiere analizar el acuerdo.",
    "La constitución de un derecho o de una servidumbre es distinta.",
    "El decreto mencionado no consta en el caso.",
    "No se aportó el reglamento contractual ni una sentencia.",
    "La palabra código, por sí sola, no identifica un texto legal.",
    "La ley puede requerir otras condiciones.",
))
def test_vocabulario_juridico_ordinario_no_es_fuente_externa(frase):
    verificar_prosa(frase, [MORA], RELATO, permitir_derivadas=True, datos_caso=DATOS)


@pytest.mark.parametrize("frase", (
    "Según la Constitución Política del Estado, se decide el caso.",
    "El artículo 14 de la Constitución establece otra regla.",
    "La CPE permite esto.",
    "La Ley Inventada establece el plazo.",
    "El Decreto Supremo N° 123 establece el plazo.",
    "El Reglamento N° 42 establece el plazo.",
    "El Código Penal establece otra consecuencia.",
))
def test_referencia_externa_identificada_se_rechaza(frase):
    with pytest.raises(RespuestaInvalida) as exc:
        verificar_prosa(frase, [MORA], RELATO, permitir_derivadas=True, datos_caso=DATOS)
    assert exc.value.motivo in {"norma_externa_en_prosa", "codigo_fuera_de_fuentes"}
    assert exc.value.detalle


def test_articulo_341_del_codigo_civil_permitido_en_su_apartado():
    fuente = SimpleNamespace(id="mora341", numero_articulo=341, codigo="Código Civil",
                             epigrafe="MORA SIN INTIMACIÓN O REQUERIMIENTO",
                             texto="La mora puede producirse sin intimación en los casos previstos.")
    texto = "El artículo 341 del Código Civil prevé supuestos de mora sin intimación."
    validar_caso_complejo([{"fuente": "F1", "cita": fuente.texto[:30], "problema": "q1",
                           "apartado": 0, "explicacion": texto}],
                          "Resumen.", "Conclusión.", [], [fuente], RELATO,
                          por_problema={"q1": ["mora341"]}, problemas=[PREGUNTAS[0]],
                          datos_caso=DATOS)


def test_articulo_real_de_otro_apartado_rechazado():
    with pytest.raises(RespuestaInvalida) as exc:
        validar([item(explicacion="El artículo 741 del Código Civil define la mora.")])
    assert exc.value.motivo == "articulo_fuera_de_fuentes"
    assert exc.value.apartado == "q1"
    assert exc.value.texto == "El artículo 741 del Código Civil define la mora."
    assert exc.value.fuente == "F1"


def test_rechazo_conserva_salida_original_y_apartado_en_debug_local(monkeypatch, tmp_path):
    monkeypatch.setenv("IA_DEBUG_RECHAZOS_DIR", str(tmp_path))
    generado = SimpleNamespace(model_dump=lambda **_: {"analisis": [{"problema": "q1",
                         "citas": ["F1C1"], "explicacion": "La CPE permite esto."}]})
    with pytest.raises(RespuestaInvalida) as capturado:
        validar([item(explicacion="La CPE permite esto.")])
    archivo = rag._guardar_rechazo_complejo(generado, capturado.value, [MORA, VICIOS], 1)
    import json
    diagnostico = json.loads(archivo.read_text(encoding="utf-8"))
    assert diagnostico["salida_estructurada_original"] == generado.model_dump()
    assert diagnostico["fallo"]["apartado"] == "q1"
    assert diagnostico["fallo"]["texto"] == "La CPE permite esto."
    assert diagnostico["fallo"]["regla"] == "norma_externa_en_prosa"
    assert diagnostico["fallo"]["valor_ofensivo"] == "CPE"
    assert diagnostico["fallo"]["fuente"]["id_prompt"] == "F1"


def test_cita_literal_valida_aceptada():
    validar([item()])


def test_pregunta_omitida_detectada():
    apartados = [SimpleNamespace(problema="q1", citas=["F1C1"], explicacion="Análisis de mora.")]
    with pytest.raises(RespuestaInvalida) as exc:
        validar([item()], apartados=apartados)
    assert exc.value.motivo == "pregunta_omitida"


def test_razonamiento_juridico_sin_fuente_rechazado():
    apartados = [SimpleNamespace(problema="q1", citas=[], explicacion="La mora quedó probada.")]
    with pytest.raises(RespuestaInvalida) as exc:
        validar([], problemas=[PREGUNTAS[0]], apartados=apartados)
    assert exc.value.motivo == "razonamiento_sin_fuente"


def test_revisor_sin_detalle_fuera_del_camino_normal():
    assert "_revisar(" not in inspect.getsource(rag.responder_caso_complejo)
