import pytest
from pydantic import ValidationError
from app.core.config import Settings
from app.core.ollama_destino import cabeceras_acceso

def test_config_falla_remoto_sin_credenciales():
    with pytest.raises(ValidationError, match="CF_ACCESS_CLIENT_ID"):
        Settings(_env_file=None, ollama_url="https://ia.ejemplo.com")

def test_config_acepta_remoto_con_credenciales():
    s = Settings(_env_file=None, ollama_url="https://ia.ejemplo.com", 
                 cf_access_client_id="id", cf_access_client_secret="secret")
    assert s.ollama_es_remoto is True
    assert s.ollama_cabeceras == {"CF-Access-Client-Id": "id", "CF-Access-Client-Secret": "secret"}

def test_config_rechaza_remoto_sin_tls():
    with pytest.raises(ValidationError, match="esquema https"):
        Settings(_env_file=None, ollama_url="http://192.168.0.1:11434",
                 cf_access_client_id="id", cf_access_client_secret="secret")

@pytest.mark.parametrize("url", [
    "http://127.0.0.1@evil.com", 
    "http://localhost/a"
])
def test_config_rechaza_disfraz_y_path(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ollama_url=url)

def test_config_acepta_local_sin_cabeceras_aunque_tenga_credenciales():
    s = Settings(_env_file=None, ollama_url="http://127.0.0.1:11434",
                 cf_access_client_id="id", cf_access_client_secret="secret")
    assert s.ollama_es_remoto is False
    assert s.ollama_cabeceras == {}

def test_cabeceras_acceso_faltantes():
    assert cabeceras_acceso("", "secret") == {}
    assert cabeceras_acceso("id", "  ") == {}
