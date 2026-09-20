from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from app.services.ia.metricas import pipeline, medir, sumar, rechazo, instantanea


def test_metricas_aisladas_entre_solicitudes_concurrentes():
    barrera = Barrier(2)

    @pipeline
    def consulta(cantidad):
        sumar("qwen_calls", cantidad)
        barrera.wait(timeout=5)
        return SimpleNamespace(trazabilidad={}, fuentes=[])

    with ThreadPoolExecutor(max_workers=2) as executor:
        resultados = list(executor.map(consulta, [1, 2]))
    assert [r.trazabilidad["metricas"]["qwen_calls"] for r in resultados] == [1, 2]
    assert instantanea() == {}


def test_fallo_restaura_contexto_y_no_loguea_datos(caplog):
    import pytest

    @pipeline
    def consulta(pregunta_privada):
        with medir("embedding"):
            rechazo("cita_no_literal")
            raise ValueError(pregunta_privada)

    with caplog.at_level("INFO"), pytest.raises(ValueError):
        consulta("CONTENIDO PRIVADO DE PRUEBA")
    assert "CONTENIDO PRIVADO" not in caplog.text
    assert "cita_no_literal" in caplog.text
    assert instantanea() == {}
