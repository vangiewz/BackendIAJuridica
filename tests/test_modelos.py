import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone
from app.models.shared.base import Base

# Importar el registro para que Base conozca todas las tablas
import app.models.shared.registro

# Enums a verificar
from app.models.shared.enums import AreaJuridica, TipoDocumento, EstadoProceso, SeveridadRiesgo, EstadoVigencia
from app.models.conocimiento.norma import Norma

SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

@pytest.fixture(scope="module", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def test_creacion_tablas():
    """Verifica que las tablas y enums definidos puedan crearse."""
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

    # EstadoVigencia
    assert EstadoVigencia.VIGENTE.value == "vigente"
    assert EstadoVigencia.DEROGADO.value == "derogado"
    assert EstadoVigencia.MODIFICADO.value == "modificado"
    assert EstadoVigencia.SIN_VERIFICAR.value == "sin_verificar"

def test_norma_area_juridica_nullable():
    """Test nuevo: se puede instanciar una Norma con area_juridica=None y persistirla."""
    with Session(engine) as session:
        norma = Norma(
            codigo="Codigo Civil",
            articulo="1",
            numero_articulo=1,
            texto="Texto de prueba",
            area_juridica=None,
            fuente_nombre="DL 12760",
            fuente_url="http://ejemplo.com",
            descargada_en=datetime.now(timezone.utc)
        )
        session.add(norma)
        session.commit()
        
        # Verify it was saved
        norma_db = session.query(Norma).filter_by(codigo="Codigo Civil", articulo="1").first()
        assert norma_db is not None
        assert norma_db.area_juridica is None

def test_norma_unique_constraint():
    """Test nuevo: dos normas con el mismo (codigo, numero_articulo, version) violan la restriccion unica."""
    with Session(engine) as session:
        norma1 = Norma(
            codigo="Codigo Procesal Civil",
            articulo="2",
            numero_articulo=2,
            texto="Texto de prueba 1",
            fuente_nombre="DL 12760",
            fuente_url="http://ejemplo.com",
            descargada_en=datetime.now(timezone.utc)
        )
        session.add(norma1)
        session.commit()
        
        norma2 = Norma(
            codigo="Codigo Procesal Civil",
            articulo="2 bis",
            numero_articulo=2,
            texto="Texto de prueba 2",
            fuente_nombre="DL 12760",
            fuente_url="http://ejemplo.com",
            descargada_en=datetime.now(timezone.utc)
        )
        session.add(norma2)
        with pytest.raises(IntegrityError):
            session.commit()
