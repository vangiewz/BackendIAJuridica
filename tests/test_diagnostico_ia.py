from app.core.config import Settings
from app.services.ia.diagnostico import diagnosticar, diagnosticar_base
from app.services.ia.ollama_client import OllamaClient, IANoDisponible


def test_base_no_configurada_sin_conexion():
    result = diagnosticar_base(Settings(_env_file=None, database_url=""))
    assert result["estado"] == "no_configurada"
    assert result["vector_store"] == "no_verificado"


def test_ollama_apagado_no_rompe_diagnostico(monkeypatch):
    def unavailable(self):
        raise IANoDisponible()
    monkeypatch.setattr(OllamaClient, "modelos", unavailable)
    result = diagnosticar(Settings(_env_file=None, database_url=""))
    assert result["ollama_disponible"] is False
    assert result["modelo_principal_disponible"] is False
    assert result["embedding_disponible"] is False
    assert "no está disponible" in result["mensaje"]


def test_importar_app_no_llama_ollama(monkeypatch):
    from app.main import create_app
    def unexpected(*args, **kwargs):
        raise AssertionError("No debe conectarse a Ollama durante el arranque")
    monkeypatch.setattr(OllamaClient, "_request", unexpected)
    assert create_app().title
