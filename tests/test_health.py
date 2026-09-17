from fastapi.testclient import TestClient
from app.main import app
import pytest

client = TestClient(app)

def test_leer_estado_health_endpoint(monkeypatch: pytest.MonkeyPatch):
    """Verifica que el endpoint de salud devuelva HTTP 200 y el estado esperado."""
    # Forzar la respuesta de verificar_conexion para no golpear la red
    monkeypatch.setattr("app.controllers.health.estado_controller.verificar_conexion", lambda: "ok")

    response = client.get("/api/v1/health")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "ok"
    assert data["app_name"] == "Asistencia Juridica Civil Boliviana"
    assert data["version"] == "0.1.0"
    assert data["environment"] == "development"
    assert "database" in data
    assert data["database"] == "ok"
