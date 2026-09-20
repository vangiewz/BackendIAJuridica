"""HU-10: el resumen y las observaciones de IA no pueden invadir el motor de riesgos."""
import json
import uuid

import httpx
import pytest

from app.core.config import Settings
from app.models.ia.esquemas import AnalisisContratoModelo, FuenteIA
from app.services.ia.ollama_client import OllamaClient, RespuestaInvalida
from app.services.ia.validacion import validar_observaciones

CONTRATO = ("CONTRATO DE ARRENDAMIENTO. SEGUNDA.- El canon mensual será de 1500 bolivianos, "
            "pagaderos del 1 al 5. TERCERA.- El plazo del contrato es de un año.")


@pytest.fixture
def fuente():
    return FuenteIA(id=uuid.uuid4(), codigo="Codigo Civil", numero_articulo=701, articulo="701",
        epigrafe=None, texto="El arrendatario debe pagar el canon en los plazos convenidos.",
        version=1, estado_vigencia="sin_verificar", fuente_nombre="fixture", fuente_url="",
        contenido_hash="fixture")


def analisis(**cambios):
    return AnalisisContratoModelo.model_validate({
        "resumen": "Arrendamiento con canon mensual y plazo de un año.",
        "observaciones": [{"evidencia": "El plazo del contrato es de un año",
                           "observacion": "Conviene revisar cómo se renueva ese plazo.",
                           "fuente": None}], **cambios})


def test_observacion_anclada_al_contrato(fuente):
    assert validar_observaciones(analisis(), [fuente], CONTRATO) == {"F1": fuente}


def test_no_se_admite_una_clausula_que_el_contrato_no_tiene(fuente):
    valor = analisis(observaciones=[{"evidencia": "El arrendatario pagará una multa del 50%",
                                     "observacion": "Esa multa es elevada.", "fuente": None}])
    with pytest.raises(RespuestaInvalida) as error:
        validar_observaciones(valor, [fuente], CONTRATO)
    assert error.value.motivo == "evidencia_fuera_del_documento"


def test_la_observacion_no_puede_invocar_articulos_ajenos(fuente):
    valor = analisis(observaciones=[{"evidencia": "El plazo del contrato es de un año",
                                     "observacion": "El artículo 9999 obliga a renovarlo.",
                                     "fuente": "F1"}])
    with pytest.raises(RespuestaInvalida) as error:
        validar_observaciones(valor, [fuente], CONTRATO)
    assert error.value.motivo == "articulo_fuera_de_fuentes"


def test_la_observacion_no_inventa_cifras(fuente):
    valor = analisis(observaciones=[{"evidencia": "El canon mensual será de 1500 bolivianos",
                                     "observacion": "Supera el tope de 9000 bolivianos.",
                                     "fuente": None}])
    with pytest.raises(RespuestaInvalida) as error:
        validar_observaciones(valor, [fuente], CONTRATO)
    assert error.value.motivo == "cifra_fuera_de_fuentes"


def test_las_cifras_del_propio_contrato_si_se_admiten(fuente):
    valor = analisis(observaciones=[{"evidencia": "El canon mensual será de 1500 bolivianos",
                                     "observacion": "El canon de 1500 se paga del 1 al 5.",
                                     "fuente": None}])
    assert validar_observaciones(valor, [fuente], CONTRATO)


def test_sin_ollama_el_analisis_de_ia_se_reporta_no_disponible(monkeypatch):
    from app.services.ia import contratos

    def handler(request):
        raise httpx.ConnectError("sin servidor")
    cliente = OllamaClient(Settings(_env_file=None), httpx.MockTransport(handler))
    monkeypatch.setattr(contratos, "_fuentes_del_contrato", lambda *a, **k: [])
    resultado = contratos.analizar_contrato(None, "arrendamiento", CONTRATO, [], [], [], cliente)
    assert resultado.disponible is False
    assert resultado.observaciones == []
    assert "no está disponible" in resultado.motivo
