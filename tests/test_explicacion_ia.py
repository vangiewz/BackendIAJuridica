"""HU-13: la explicación acompaña al texto original, nunca lo sustituye ni lo amplía."""
import json
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import Settings
from app.services.ia.explicacion import explicar_articulo
from app.services.ia.ollama_client import OllamaClient

TEXTO = ("Quien con un hecho doloso o culposo, ocasiona a alguien un daño injusto, "
         "queda obligado al resarcimiento.")


@pytest.fixture
def norma():
    return SimpleNamespace(
        id="8c6d0f3a-0000-4000-8000-000000000001", codigo="Codigo Civil", numero_articulo=984,
        articulo="984", epigrafe="Resarcimiento por hecho ilícito", texto=TEXTO, version=1,
        activa=True, estado_vigencia="sin_verificar", fuente_nombre="fixture", fuente_url="",
        libro="Libro Tercero", parte=None, titulo="De los hechos ilícitos", capitulo=None,
        seccion=None, area_juridica=None, nota_vigencia=None, vigente_desde=None,
        vigente_hasta=None, descargada_en=None)


def cliente(salida):
    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion"]})
        if request.url.path == "/api/chat":
            return httpx.Response(200, json={"done": True, "message": {
                "content": json.dumps(salida, ensure_ascii=False)}})
        return httpx.Response(200, json={"models": []})
    return OllamaClient(Settings(_env_file=None), httpx.MockTransport(handler))


def test_devuelve_texto_original_y_explicacion(norma):
    resultado = explicar_articulo(norma, cliente({
        "explicacion": "Si alguien causa un daño a otro, con intención o por descuido, debe repararlo.",
        "ejemplo": "Una persona rompe algo de un vecino y debe repararlo."}))
    assert resultado.disponible
    assert resultado.texto_original == TEXTO
    assert resultado.ejemplo
    assert resultado.trazabilidad["intentos_validacion"] == 1


def test_no_se_admite_traer_otro_articulo(norma):
    resultado = explicar_articulo(norma, cliente({
        "explicacion": "El artículo 1000 amplía esta regla a otros casos de daño.", "ejemplo": ""}))
    assert resultado.disponible is False
    assert resultado.trazabilidad["validacion_motivo"] == "articulo_fuera_de_fuentes"
    # Aunque falle, el texto original sigue disponible para el usuario.
    assert resultado.texto_original == TEXTO


def test_no_se_admite_inventar_un_plazo(norma):
    resultado = explicar_articulo(norma, cliente({
        "explicacion": "El daño debe reclamarse dentro de los 30 días siguientes.", "ejemplo": ""}))
    assert resultado.disponible is False
    assert resultado.trazabilidad["validacion_motivo"] == "cifra_fuera_de_fuentes"


def test_ollama_caido_devuelve_el_articulo_sin_explicacion(norma):
    def handler(request):
        raise httpx.ConnectError("sin servidor")
    resultado = explicar_articulo(norma, OllamaClient(
        Settings(_env_file=None), httpx.MockTransport(handler)))
    assert resultado.disponible is False
    assert resultado.texto_original == TEXTO
    assert "no está disponible" in resultado.motivo
