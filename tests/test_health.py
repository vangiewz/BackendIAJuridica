from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_leer_estado_health_endpoint():
    """Verifica que el endpoint de salud devuelva HTTP 200 y el estado esperado."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "ok"
    assert data["app_name"] == "Asistencia Juridica Civil Boliviana"
    assert data["version"] == "0.1.0"
    assert data["environment"] == "development"
