import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from app.models.shared.base import Base

# Importar el registro para que Base conozca todas las tablas
import app.models.shared.registro

# Enums a verificar
from app.models.shared.enums import AreaJuridica, TipoDocumento, EstadoProceso, SeveridadRiesgo

SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

def test_creacion_tablas():
    """Verifica que las tablas y enums definidos puedan crearse."""
    # Esto creara las tablas en memoria y validara la estructura basica
    Base.metadata.create_all(bind=engine)
    
    # Verificar que existen las tablas clave creadas
    assert "usuarios" in Base.metadata.tables
    assert "consultas" in Base.metadata.tables
    assert "fuentes_legales" in Base.metadata.tables
    assert "normas" in Base.metadata.tables
    assert "documentos" in Base.metadata.tables
    assert "analisis_documentos" in Base.metadata.tables
    assert "comparaciones_documentos" in Base.metadata.tables
    assert "riesgos_contractuales" in Base.metadata.tables
    assert "documentos_generados" in Base.metadata.tables

def test_valores_enums():
    """Verifica que los enums se definan en minusculas para postgresql."""
    # AreaJuridica
    assert AreaJuridica.CONTRATOS.value == "contratos"
    assert AreaJuridica.OBLIGACIONES.value == "obligaciones"
    assert AreaJuridica.DERECHOS_REALES.value == "derechos_reales"
    assert AreaJuridica.SUCESIONES.value == "sucesiones"
    assert AreaJuridica.RESPONSABILIDAD_CIVIL.value == "responsabilidad_civil"
    
    # TipoDocumento
    assert TipoDocumento.COMPRAVENTA.value == "compraventa"
    assert TipoDocumento.ARRENDAMIENTO.value == "arrendamiento"
    assert TipoDocumento.PRESTAMO.value == "prestamo"
    assert TipoDocumento.ACUERDO_CIVIL.value == "acuerdo_civil"
    assert TipoDocumento.OTRO.value == "otro"
    
    # EstadoProceso
    assert EstadoProceso.PENDIENTE.value == "pendiente"
    assert EstadoProceso.PROCESANDO.value == "procesando"
    assert EstadoProceso.COMPLETADO.value == "completado"
    assert EstadoProceso.FALLIDO.value == "fallido"
    
    # SeveridadRiesgo
    assert SeveridadRiesgo.ALTA.value == "alta"
    assert SeveridadRiesgo.MEDIA.value == "media"
    assert SeveridadRiesgo.BAJA.value == "baja"
