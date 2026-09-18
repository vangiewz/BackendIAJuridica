from app.services.conocimiento.mapeo_areas import area_de
from app.models.shared.enums import AreaJuridica

def test_area_de():
    assert area_de(1) is None
    assert area_de(73) is None
    assert area_de(74) == AreaJuridica.DERECHOS_REALES
    assert area_de(290) == AreaJuridica.DERECHOS_REALES
    assert area_de(291) == AreaJuridica.OBLIGACIONES
    assert area_de(449) == AreaJuridica.OBLIGACIONES
    assert area_de(450) == AreaJuridica.CONTRATOS
    assert area_de(954) == AreaJuridica.CONTRATOS
    assert area_de(955) == AreaJuridica.OBLIGACIONES
    assert area_de(983) == AreaJuridica.OBLIGACIONES
    assert area_de(984) == AreaJuridica.RESPONSABILIDAD_CIVIL
    assert area_de(999) == AreaJuridica.RESPONSABILIDAD_CIVIL
    assert area_de(1000) == AreaJuridica.SUCESIONES
    assert area_de(1278) == AreaJuridica.SUCESIONES
    assert area_de(1279) is None
    assert area_de(1570) is None
