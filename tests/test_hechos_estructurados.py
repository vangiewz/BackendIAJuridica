"""Garantías por ID del caso complejo; ninguna prueba llama a Ollama."""
from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from app.models.ia.esquemas import AnalisisProblemaModelo, RespuestaCasoComplejo
from app.services.ia import rag
from app.services.ia.casos import (derivaciones_verificadas, hechos_estructurados,
                                   problemas_de_preguntas)
from app.services.ia.fragmentos import resolver_citas_complejo
from app.services.ia.ollama_client import RespuestaInvalida
from app.services.ia.prompts import construir_prompt
from app.services.ia.validacion import renderizar_hechos, validar_caso_complejo


RELATO = (Path(__file__).parent / "fixtures/caso_remodelacion.txt").read_text(encoding="utf-8")
HECHOS = hechos_estructurados(RELATO)
DERIVACIONES = derivaciones_verificadas(HECHOS)
PREGUNTAS = {p.clave: p for p in problemas_de_preguntas(RELATO)}
MORA = SimpleNamespace(id="mora", numero_articulo=341, codigo="Código Civil",
                       epigrafe="MORA SIN INTIMACIÓN O REQUERIMIENTO",
                       texto="La mora sin intimación o requerimiento procede en los supuestos descritos por la norma.")
SALDO = SimpleNamespace(id="saldo", numero_articulo=573, codigo="Código Civil",
                        epigrafe="EXCEPCIÓN DEL INCUMPLIMIENTO DE CONTRATO",
                        texto="En los contratos con prestaciones recíprocas se puede oponer la excepción de incumplimiento.")
PENA = SimpleNamespace(id="pena", numero_articulo=532, codigo="Código Civil",
                       epigrafe="RESARCIMIENTO CONVENCIONAL",
                       texto="La pena convencional sustituye al resarcimiento del daño causado por el retraso.")


def apartado(q="q1", *, hechos=(), derivaciones=(), aplicacion="Con los hechos aportados debe analizarse la mora.",
             citas=("F1C1",), estado="fundamentado", regla="La fuente prevé condiciones para la mora."):
    return AnalisisProblemaModelo(
        pregunta_id=q, problema=q, estado=estado, hechos_usados=list(hechos),
        derivaciones_usadas=list(derivaciones), citas=list(citas), regla=regla,
        aplicacion=aplicacion, conclusion="La consecuencia requiere comprobar esos requisitos.")


def validar(apartados, fuentes=None, problemas=None, mapa=None):
    fuentes = fuentes or [MORA]
    problemas = problemas or [PREGUNTAS[a.pregunta_id] for a in apartados]
    mapa = mapa or {p.clave: [str(f.id) for f in fuentes] for p in problemas}
    generado = RespuestaCasoComplejo(resumen="Se relata una obra contratada.",
                                     analisis=apartados, conclusion="Debe examinarse cada cuestión.")
    items = resolver_citas_complejo(generado, fuentes)
    return validar_caso_complejo(items, generado.resumen, generado.conclusion, [],
                                 fuentes, RELATO, por_problema=mapa, problemas=problemas,
                                 hechos=HECHOS, derivaciones=DERIVACIONES,
                                 apartados=generado.analisis)


def test_ids_y_calculo_con_operandos_inmutables():
    assert HECHOS["H1"]["valor"] == "180000"
    assert HECHOS["H3"]["tipo"] == "saldo_pendiente" and HECHOS["H3"]["valor"] == "108000"
    assert HECHOS["H4"]["tipo"] == "gasto_adicional" and HECHOS["H4"]["valor"] == "28000"
    assert HECHOS["H5"]["valor"] == "0.5"
    assert HECHOS["H7"]["valor"] == "2026-04-30"
    assert HECHOS["H8"]["valor"] == "2026-05-05"
    assert HECHOS["H9"]["valor"] == "5"
    assert HECHOS["H10"]["valor"] == "2026-05-18"
    assert DERIVACIONES["D1"]["base_fact_id"] == "H1"
    assert DERIVACIONES["D1"]["porcentaje_fact_id"] == "H6"
    assert DERIVACIONES["D1"]["resultado"] == "18000.00"
    with pytest.raises(TypeError):
        HECHOS["H7"]["valor"] = "2026-05-18"
    with pytest.raises(TypeError):
        DERIVACIONES["D1"]["resultado"] = "0"


def test_prompt_usa_nueve_preguntas_y_catalogos_tipados():
    problemas = list(PREGUNTAS.values())
    mensajes, usadas = construir_prompt(RELATO, [MORA], citas_identificadas=True,
                                        problemas=problemas, por_problema={"q1": ["mora"]},
                                        hechos_caso=HECHOS, derivaciones=DERIVACIONES)
    cuerpo = json.loads(mensajes[1]["content"])
    assert len(cuerpo["PROBLEMAS"]) == 9 and len(usadas) == 1
    assert cuerpo["HECHOS_CASO"]["H10"]["tipo"] == "fecha_abandono"
    assert cuerpo["DERIVACIONES_VERIFICADAS"]["D1"]["base_fact_id"] == "H1"


def test_vencimiento_y_abandono_en_una_oracion_no_producen_falso_positivo():
    texto = "La obra vencía el {{fecha_vencimiento:H7}} y fue abandonada el {{fecha_abandono:H10}}."
    validar([apartado(hechos=("H7", "H10"), aplicacion=texto)])
    visible = renderizar_hechos(texto, HECHOS, DERIVACIONES)
    assert "30 de abril de 2026" in visible and "18 de mayo de 2026" in visible


def test_flujo_estructurado_no_usa_asociacion_por_proximidad(monkeypatch):
    from app.services.ia import validacion
    monkeypatch.setattr(validacion, "validar_asociaciones_cifras",
                        lambda *_args: (_ for _ in ()).throw(AssertionError("validador antiguo invocado")))
    validar([apartado(hechos=("H7", "H10"),
                      aplicacion="El plazo venció {{fecha_vencimiento:H7}} y la obra fue abandonada {{fecha_abandono:H10}}.")])


def test_h10_no_puede_ser_plazo_adicional():
    with pytest.raises(RespuestaInvalida) as exc:
        validar([apartado(hechos=("H10",), aplicacion="El plazo terminó {{plazo_adicional:H10}}.")])
    assert exc.value.motivo == "rol_de_hecho_incorrecto"
    assert exc.value.apartado == "q1"


def test_h4_no_puede_convertirse_en_saldo():
    with pytest.raises(RespuestaInvalida) as exc:
        validar([apartado("q7", hechos=("H4",),
                          aplicacion="Respecto de {{saldo_pendiente:H4}}, debe examinarse el cumplimiento.",
                          regla="La excepción depende del cumplimiento recíproco.")],
                fuentes=[SALDO])
    assert exc.value.motivo == "rol_de_hecho_incorrecto"


def test_h3_si_es_saldo():
    validar([apartado("q7", hechos=("H3",),
                      aplicacion="Respecto de {{saldo_pendiente:H3}}, debe examinarse el cumplimiento.",
                      regla="La excepción depende del cumplimiento recíproco.")], fuentes=[SALDO])


def test_porcentaje_libre_5_se_rechaza():
    with pytest.raises(RespuestaInvalida) as exc:
        validar([apartado("q4", hechos=("H5",),
                          aplicacion="La penalidad diaria pactada es 5%.",
                          regla="La pena convencional puede sustituir el resarcimiento.")], fuentes=[PENA])
    assert exc.value.motivo == "cifra_sin_hecho_id"


def test_d1_calculado_por_backend_pasa():
    texto = ("El tope {{limite_penalidad:H6}} sobre {{precio_total:H1}} "
             "produce {{tope_calculado:D1}}.")
    validar([apartado("q4", hechos=("H1", "H6"), derivaciones=("D1",),
                      aplicacion=texto, regla="La pena convencional tiene sus condiciones.")],
            fuentes=[PENA])
    assert "Bs 18.000" in renderizar_hechos(texto, HECHOS, DERIVACIONES)


def test_77_dias_sin_derivacion_se_rechaza():
    with pytest.raises(RespuestaInvalida) as exc:
        validar([apartado(aplicacion="Hubo 77 días de retraso.")])
    assert exc.value.motivo == "cifra_sin_hecho_id"


def test_pregunta_q1_omitida_se_detecta():
    with pytest.raises(RespuestaInvalida) as exc:
        validar([apartado("q7", regla="La excepción depende del cumplimiento recíproco.")],
                fuentes=[SALDO], problemas=[PREGUNTAS["q1"], PREGUNTAS["q7"]],
                mapa={"q1": [], "q7": ["saldo"]})
    assert exc.value.motivo == "pregunta_omitida"
    assert exc.value.detalle == "q1"


def test_q1_duplicada_se_rechaza():
    with pytest.raises(RespuestaInvalida) as exc:
        validar([apartado(), apartado()])
    assert exc.value.motivo == "apartado_duplicado"


def test_fuente_de_otro_problema_se_rechaza():
    with pytest.raises(RespuestaInvalida) as exc:
        validar([apartado(citas=("F2C1",))], fuentes=[MORA, SALDO],
                mapa={"q1": ["mora"]})
    assert exc.value.motivo == "fuente_de_otro_problema"


def test_regla_juridica_sin_cita_se_rechaza():
    with pytest.raises(RespuestaInvalida) as exc:
        validar([apartado(citas=(), regla="La ley concede resolución automática.")])
    assert exc.value.motivo == "razonamiento_sin_fuente"


def test_estado_sin_fuente_no_puede_disfrazar_regla_juridica():
    with pytest.raises(RespuestaInvalida) as exc:
        validar([apartado(citas=(), estado="sin_fuente_suficiente",
                          regla="La ley concede resolución automática.",
                          aplicacion="No puedo fundamentar el efecto jurídico con las fuentes.")])
    assert exc.value.motivo == "regla_sin_cita"


def test_informacion_adicional_sin_regla_juridica_es_valida():
    validar([apartado("q9", citas=(), regla="",
                      aplicacion="Hace falta conocer si hubo recepción formal de la obra.",
                      estado="fundamentado")], fuentes=[MORA], mapa={"q9": []})


def test_aplicacion_razonada_no_necesita_ser_cita_literal():
    validar([apartado(hechos=("H7", "H8"),
                      aplicacion=("El vencimiento {{fecha_vencimiento:H7}} y la posterior "
                                  "comunicación {{fecha_requerimiento:H8}} permiten analizar "
                                  "si hubo mora, sujeto a los requisitos de la fuente."))])


def test_diagnostico_incluye_ids_de_hechos_y_fuentes(monkeypatch, tmp_path):
    monkeypatch.setenv("IA_DEBUG_RECHAZOS_DIR", str(tmp_path))
    a = apartado(hechos=("H10",), aplicacion="El plazo terminó {{plazo_adicional:H10}}.")
    generado = RespuestaCasoComplejo(resumen="Resumen.", analisis=[a], conclusion="Conclusión.")
    with pytest.raises(RespuestaInvalida) as exc:
        validar_caso_complejo(resolver_citas_complejo(generado, [MORA]), generado.resumen,
                               generado.conclusion, [], [MORA], RELATO,
                               por_problema={"q1": ["mora"]}, problemas=[PREGUNTAS["q1"]],
                               hechos=HECHOS, derivaciones=DERIVACIONES, apartados=[a])
    ruta = rag._guardar_rechazo_complejo(generado, exc.value, [MORA], 1, {"q1": ["mora"]})
    fallo = json.loads(ruta.read_text(encoding="utf-8"))["fallo"]
    assert fallo["pregunta_id"] == "q1"
    assert fallo["hechos_usados"] == ["H10"]
    assert fallo["fuente_ids"] == ["mora"]
    assert fallo["cita_ids"] == ["F1C1"]
    assert fallo["valor_ofensivo"] == "{{plazo_adicional:H10}}"
