"""Humo de infraestructura, sin datos privados ni afirmaciones jurídicas gold."""
import os
import pytest
from pydantic import BaseModel, ConfigDict
from app.services.ia.ollama_client import OllamaClient, IAError

pytestmark = [pytest.mark.ia_local, pytest.mark.skipif(
    os.getenv("RUN_IA_LOCAL") != "1", reason="Activar RUN_IA_LOCAL=1 explícitamente")]


@pytest.fixture
def client():
    client = OllamaClient()
    try:
        modelos = client.modelos()
    except IAError:
        pytest.skip("Ollama no disponible")
    if client.settings.ollama_model not in modelos or client.settings.embedding_model not in modelos:
        pytest.skip("Falta alguno de los modelos locales")
    return client


def test_embedding_real(client):
    vectors = client.embeddings(["prueba técnica de disponibilidad"])
    assert len(vectors) == 1
    assert len(vectors[0]) > 0


def test_json_real(client):
    class Salida(BaseModel):
        model_config = ConfigDict(extra="forbid")
        disponible: bool
    result = client.generar([
        {"role": "system", "content": "Devuelve JSON con disponible=true. Es una prueba técnica."},
        {"role": "user", "content": "Comprueba disponibilidad."},
    ], Salida)
    assert result.disponible is True
