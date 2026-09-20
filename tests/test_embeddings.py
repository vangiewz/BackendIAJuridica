import json
from uuid import uuid4

import httpx
import pytest

from app.core.config import Settings
from app.models.conocimiento.norma import Norma
from app.services.ia.embeddings import documento_norma, huella_documento
from app.services.ia.ollama_client import OllamaClient, RespuestaInvalida


@pytest.mark.parametrize("vectors", [[], [[0, 0]], [[1], [1, 2]], [[True]], [["1"]], None])
def test_vectores_invalidos(vectors):
    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["embedding"]})
        return httpx.Response(200, json={"embeddings": vectors})
    client = OllamaClient(Settings(_env_file=None), httpx.MockTransport(handler))
    with pytest.raises(RespuestaInvalida):
        client.embeddings(["texto"])


def test_dimension_medida_y_sin_truncamiento():
    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["embedding"]})
        body = json.loads(request.content)
        assert body["truncate"] is False
        assert "dimensions" not in body
        return httpx.Response(200, json={"embeddings": [[0.2, 0.8, -0.5]]})
    client = OllamaClient(Settings(_env_file=None), httpx.MockTransport(handler))
    assert len(client.embeddings(["texto"])[0]) == 3


def test_hash_cambia_con_texto_version_y_vigencia():
    # Datos sintéticos exclusivamente para probar serialización, no evaluación jurídica.
    norma = Norma(id=uuid4(), codigo="fixture", articulo="fixture", numero_articulo=1,
                  texto="texto de prueba", activa=True, version=1)
    before = huella_documento(documento_norma(norma))
    for field, value in [("texto", "otro texto"), ("version", 2), ("nota_vigencia", "revisar")]:
        setattr(norma, field, value)
        after = huella_documento(documento_norma(norma))
        assert before != after
        before = after
    norma.activa = False
    with pytest.raises(ValueError):
        documento_norma(norma)
