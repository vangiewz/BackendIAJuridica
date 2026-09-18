import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from pathlib import Path
import re

from app.models.shared.base import Base
from app.models.conocimiento.norma import Norma
from app.services.conocimiento.parser_articulos import ArticuloParseado
from app.services.conocimiento.perfiles_fuente import PerfilFuente
from app.controllers.conocimiento.errores import CorpusIncompletoError
from app.controllers.conocimiento.ingesta_controller import ingerir_articulos
from app.models.shared.enums import EstadoVigencia, AreaJuridica

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

@pytest.fixture
def perfil_test():
    return PerfilFuente(
        codigo="Codigo Civil",
        fuente_nombre="Test InfoLeyes",
        fuente_url="https://test.com/codigo.pdf",
        archivo="test.pdf",
        total_esperado=3,
        ruido=re.compile(r'^$'),
        inicio_articulo=re.compile(r'^ART'),
        nivel=re.compile(r'^$')
    )

def test_corpus_incompleto_lanza_error_y_no_escribe(db_session: Session, perfil_test: PerfilFuente):
    articulos = [
        ArticuloParseado(1, "1", "Epi 1", "Texto 1", "LIBRO I", None, None, None, None)
    ]
    
    with pytest.raises(CorpusIncompletoError):
        ingerir_articulos(
            db=db_session, 
            articulos=articulos, 
            perfil=perfil_test, 
            descargada_en=datetime.now(timezone.utc)
        )
    
    count = db_session.execute(select(Norma)).scalars().all()
    assert len(count) == 0

def test_ingesta_es_idempotente(db_session: Session, perfil_test: PerfilFuente):
    ahora = datetime.now(timezone.utc)
    articulos_v1 = [
        ArticuloParseado(1, "1", "Epi 1", "Texto original 1", "LIBRO I", None, None, None, None),
        ArticuloParseado(75, "75", "Epi 75", "Texto 75", "LIBRO II", None, None, None, None),
        ArticuloParseado(1000, "1000", "Epi 1000", "Texto 1000", "LIBRO IV", None, None, None, None),
    ]

    reporte1 = ingerir_articulos(db_session, articulos_v1, perfil_test, ahora)
    db_session.commit()
    assert reporte1.insertadas == 3
    
    count1 = db_session.execute(select(Norma)).scalars().all()
    assert len(count1) == 3
    
    reporte2 = ingerir_articulos(db_session, articulos_v1, perfil_test, ahora)
    db_session.commit()
    
    assert reporte2.insertadas == 0
    assert reporte2.actualizadas == 0
    assert reporte2.sin_cambios == 3
    
    count2 = db_session.execute(select(Norma)).scalars().all()
    assert len(count2) == 3

def test_actualizar_texto_crea_version_nueva(db_session: Session, perfil_test: PerfilFuente):
    ahora = datetime.now(timezone.utc)
    articulos_v1 = [
        ArticuloParseado(1, "1", "Epi 1", "Texto original 1", "LIBRO I", None, None, None, None),
        ArticuloParseado(75, "75", "Epi 75", "Texto 75", "LIBRO II", None, None, None, None),
        ArticuloParseado(1000, "1000", "Epi 1000", "Texto 1000", "LIBRO IV", None, None, None, None),
    ]
    ingerir_articulos(db_session, articulos_v1, perfil_test, ahora)
    db_session.commit()
    
    articulos_v2 = [
        ArticuloParseado(1, "1", "Epi 1", "Texto modificado 1", "LIBRO I", None, None, None, None),
        ArticuloParseado(75, "75", "Epi 75", "Texto 75", "LIBRO II", None, None, None, None),
        ArticuloParseado(1000, "1000", "Epi 1000", "Texto 1000", "LIBRO IV", None, None, None, None),
    ]
    reporte3 = ingerir_articulos(db_session, articulos_v2, perfil_test, ahora)
    db_session.commit()
    
    assert reporte3.actualizadas == 1
    assert reporte3.sin_cambios == 2
    
    normas_art1 = db_session.execute(
        select(Norma).where(Norma.numero_articulo == 1).order_by(Norma.version)
    ).scalars().all()
    
    assert len(normas_art1) == 2
    assert normas_art1[0].version == 1
    assert not normas_art1[0].activa
    assert normas_art1[0].vigente_hasta is not None
    
    assert normas_art1[1].version == 2
    assert normas_art1[1].activa
    assert normas_art1[1].vigente_hasta is None
    assert normas_art1[1].texto == "Texto modificado 1"
