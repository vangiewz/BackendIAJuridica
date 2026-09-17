from app.core.database import normalizar_url

def test_normalizar_url():
    # Vacío
    assert normalizar_url("") == ""
    assert normalizar_url(None) is None
    
    # URL normal
    url = "postgresql://user:pass@host:5432/db"
    assert normalizar_url(url) == "postgresql+psycopg://user:pass@host:5432/db"
    
    # URL que ya tiene psycopg
    url2 = "postgresql+psycopg://user:pass@host/db"
    assert normalizar_url(url2) == url2

from app.core.database import verificar_conexion
from app.core.config import Settings

def test_verificar_conexion_sin_url(monkeypatch):
    monkeypatch.setattr('app.core.database.get_settings', lambda: Settings(database_url=''))
    # Reiniciar estado global por las dudas
    import app.core.database
    monkeypatch.setattr(app.core.database, '_engine', None)
    assert verificar_conexion() == 'no configurada'

