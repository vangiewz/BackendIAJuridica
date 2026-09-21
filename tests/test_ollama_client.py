import httpx
import pytest
from pydantic import BaseModel, ValidationError
from app.core.config import Settings
from app.services.ia.ollama_client import OllamaClient, IANoDisponible, RespuestaInvalida


class Resultado(BaseModel):
    texto: str


def cliente(handler):
    return OllamaClient(Settings(_env_file=None), httpx.MockTransport(handler))


from app.services.ia.cache_modelos import limpiar_cache

@pytest.fixture(autouse=True)
def _limpiar_cache():
    limpiar_cache()
    yield

def cliente_config(handler, settings_kwargs):
    return OllamaClient(Settings(_env_file=None, **settings_kwargs), httpx.MockTransport(handler))

def test_transporte_local_sin_cabeceras():
    peticiones = []
    def handler(request):
        peticiones.append(request)
        return httpx.Response(200, json={"models": []})
    
    # ollama_url por defecto es local
    cliente_config(handler, {"cf_access_client_id": "id", "cf_access_client_secret": "sec"}).modelos()
    assert "CF-Access-Client-Id" not in peticiones[0].headers

def test_transporte_remoto_con_cabeceras():
    peticiones = []
    def handler(request):
        peticiones.append(request)
        return httpx.Response(200, json={"models": []})
    
    cliente_config(handler, {"ollama_url": "https://ia.ejemplo.com", "cf_access_client_id": "id", "cf_access_client_secret": "sec"}).modelos()
    assert peticiones[0].headers["cf-access-client-id"] == "id"
    assert peticiones[0].headers["cf-access-client-secret"] == "sec"


def test_timeout_seguro():
    def handler(request):
        raise httpx.ReadTimeout("datos privados")
    with pytest.raises(IANoDisponible, match="no está disponible"):
        cliente(handler).modelos()


@pytest.mark.parametrize("status", [302, 404, 500])
def test_errores_http(status):
    with pytest.raises(IANoDisponible):
        cliente(lambda r: httpx.Response(status)).modelos()


def test_json_invalido():
    with pytest.raises(RespuestaInvalida):
        cliente(lambda r: httpx.Response(200, text="no json")).modelos()


def test_salida_estructurada_y_reintento():
    attempts = []
    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion"]})
        attempts.append(request)
        return httpx.Response(200, json={"done": True, "message": {
            "content": 'invalid' if len(attempts) == 1 else '{"texto":"ok"}'}})
    assert cliente(handler).generar([], Resultado).texto == "ok"
    assert len(attempts) == 2


def test_reintento_limitado():
    calls = []
    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion"]})
        calls.append(1)
        return httpx.Response(200, json={"done": True, "message": {"content": '{}'}})
    with pytest.raises(RespuestaInvalida) as exc:
        cliente(handler).generar([], Resultado)
    assert len(calls) == 2
    assert exc.value.salida_estructurada_original == {}


def test_modelo_remoto_rechazado():
    with pytest.raises(IANoDisponible):
        cliente(lambda r: httpx.Response(200, json={"remote_host": "https://ollama.com"})).generar([], Resultado)
