"""Las suites normales verifican el backend sin llamar al servidor de IA."""
import pytest
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def ia_solo_en_pruebas_explicitas(request, monkeypatch):
    if request.node.get_closest_marker("ia_local") is None:
        monkeypatch.setattr(get_settings(), "ia_enabled", False)


@pytest.fixture(autouse=True)
def aislar_dependencias_integracion(request):
    if request.node.get_closest_marker("integracion") is None:
        yield
        return
    from app.main import app
    previous = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
