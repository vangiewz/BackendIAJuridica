import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.dependencias import usuario_actual
from app.services.ayuda.asistente import SolicitudAyuda, conversar
from app.services.ayuda.catalogo import catalogo_para


@pytest.mark.parametrize("pantalla,pregunta,elemento,tipo,fragmento,estado", [
    ("generar", "¿Qué hago en esta pantalla?", None, "prestamo", "Generar borrador", "ayuda"),
    ("generar", "¿Este campo es obligatorio?", "garantia", "prestamo", "opcional", "ayuda"),
    ("generar", "¿Qué pongo acá?", "garantia", "prestamo", "garantía ofrecida", "ayuda"),
    ("generar", "¿Me das un ejemplo?", "garantia", "prestamo", "si pactaron una garantía", "ayuda"),
    ("generar", "¿Qué hago después de completar el formulario?", None, "prestamo", "Generar borrador", "ayuda"),
    ("reportes", "¿Qué significa agrupar?", None, None, "valor común", "ayuda"),
    ("reportes", "¿Para qué sirve este botón?", "filtrar", None, "condición", "ayuda"),
    ("reportes", "¿Cómo lo exporto a Excel?", None, None, "Excel", "ayuda"),
    ("asistente", "¿Cuál es la diferencia entre guardar y analizar?", None, None, "Guardar", "ayuda"),
    ("generar", "¿Es legal esta cláusula?", None, None, "consulta jurídica", "redirigir_juridico"),
    ("asistente", "¿Cómo cambio mi documento activo?", None, None, "icono de cambio", "ayuda"),
    ("documentos", "¿Cómo comparo dos documentos?", None, None, "Comparar", "ayuda"),
    ("generar", "¿Cómo envío este contrato directamente al juzgado?", None, None, "No encuentro", "ayuda"),
])
def test_diez_casos_sin_modelo(pantalla, pregunta, elemento, tipo, fragmento, estado):
    class NuncaQwen:
        def generar(self, *args, **kwargs):
            pytest.fail("Esta duda de uso debe resolverse con el catálogo")

    respuesta = conversar(SolicitudAyuda(
        pregunta=pregunta, pantalla=pantalla, elemento=elemento,
        tipo_documento=tipo), client=NuncaQwen())
    assert fragmento.lower() in respuesta.respuesta.lower()
    assert respuesta.tipo == estado
    if estado == "redirigir_juridico":
        assert respuesta.accion_sugerida.destino == "asistente"


def test_campos_reales_salen_de_la_plantilla():
    prestamo = catalogo_para("generar", "prestamo")
    garantia = prestamo["campos"]["garantia"]
    assert garantia["obligatorio"] is False
    assert garantia["destacado"] is True
    assert "garantia" not in catalogo_para("generar", "compraventa")["campos"]
    assert "garantia" not in catalogo_para("generar")["campos"]


def test_endpoint_exige_sesion_y_valida_contexto():
    cliente = TestClient(app)
    respuesta = cliente.post("/api/v1/ayuda/chat", json={
        "pantalla": "reportes", "pregunta": "¿Qué significa agrupar?"})
    assert respuesta.status_code == 401
    app.dependency_overrides[usuario_actual] = lambda: SimpleNamespace(id="prueba")
    try:
        catalogo = cliente.get("/api/v1/ayuda/pantallas/generar",
                               params={"tipo_documento": "prestamo"})
        assert catalogo.status_code == 200
        assert catalogo.json()["campos"]["garantia"]["obligatorio"] is False
        respuesta = cliente.post("/api/v1/ayuda/chat", json={
            "pantalla": "reportes", "pregunta": "¿Qué significa agrupar?"})
        assert respuesta.status_code == 200
        assert respuesta.json()["tipo"] == "ayuda"
        invalida = cliente.post("/api/v1/ayuda/chat", json={
            "pantalla": "inventada", "pregunta": "¿Qué hago aquí?"})
        assert invalida.status_code == 422
    finally:
        app.dependency_overrides.pop(usuario_actual, None)


def test_qwen_solo_recibe_catalogo_actual_y_texto_redactado():
    class ClienteCaptura:
        def generar(self, mensajes, esquema, intentos=1):
            datos = json.loads(mensajes[1]["content"])
            assert datos["CATALOGO"]["titulo"] == "Generar documento"
            assert "Juan Pérez" not in mensajes[1]["content"]
            assert "CI 1234567" not in mensajes[1]["content"]
            assert "Bs 85000" not in mensajes[1]["content"]
            assert "reportes" not in datos["CATALOGO"]["acciones"]
            return esquema(respuesta="Existe un botón inventado para registrar la garantía.",
                           tipo="ayuda", referencias=["garantia", "inventado"], destino=None)

    respuesta = conversar(SolicitudAyuda(
        pregunta="¿Podés ampliar esa explicación?", pantalla="generar", elemento="garantia",
        tipo_documento="prestamo", historial=[{
            "pregunta": "Juan Pérez CI 1234567 ofreció Bs 85000",
            "respuesta": "Revisá el campo garantía."}]), client=ClienteCaptura())
    assert respuesta.tipo == "ayuda"
    assert respuesta.elemento_relacionado == "garantia"
    assert "botón inventado" not in respuesta.respuesta
    assert "opcional" in respuesta.respuesta


def test_clasificacion_erronea_del_modelo_se_corrige_con_catalogo():
    class ClienteErrado:
        def generar(self, mensajes, esquema, intentos=1):
            return esquema(respuesta="Deberías ir al asistente jurídico.",
                           tipo="redirigir_juridico", referencias=[], destino="asistente")

    respuesta = conversar(SolicitudAyuda(
        pregunta="¿Cuál es la diferencia entre tabla y resumen?",
        pantalla="reportes", modo_reporte="visual"), client=ClienteErrado())
    assert respuesta.tipo == "ayuda"
    assert "tabla" in respuesta.respuesta
    assert respuesta.accion_sugerida is None


def test_funcion_inexistente_sin_referencia_no_se_inventa():
    class ClienteSinReferencia:
        def generar(self, mensajes, esquema, intentos=1):
            return esquema(respuesta="Hay un botón para enviar al juzgado.",
                           tipo="ayuda", referencias=["inexistente"], destino=None)

    respuesta = conversar(SolicitudAyuda(
        pregunta="¿Dónde está el botón teletransportar?", pantalla="reportes"),
        client=ClienteSinReferencia())
    assert "No encuentro" in respuesta.respuesta


def test_modelo_puede_redirigir_una_duda_juridica_no_literal():
    class ClienteJuridico:
        def generar(self, mensajes, esquema, intentos=1):
            return esquema(respuesta="Consulta jurídica", tipo="redirigir_juridico",
                           referencias=[], destino="asistente")

    respuesta = conversar(SolicitudAyuda(
        pregunta="¿Puedo rescindir el contrato?", pantalla="generar"),
        client=ClienteJuridico())
    assert respuesta.tipo == "redirigir_juridico"
    assert respuesta.accion_sugerida.destino == "asistente"
