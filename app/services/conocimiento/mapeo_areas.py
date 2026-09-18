from app.models.shared.enums import AreaJuridica

def area_de(numero: int) -> AreaJuridica | None:
    """Area juridica segun la ubicacion del articulo en el Codigo Civil (nunca un juicio)."""
    if 1 <= numero <= 73:
        return None
    elif 74 <= numero <= 290:
        return AreaJuridica.DERECHOS_REALES
    elif 291 <= numero <= 449:
        return AreaJuridica.OBLIGACIONES
    elif 450 <= numero <= 954:
        return AreaJuridica.CONTRATOS
    elif 955 <= numero <= 983:
        return AreaJuridica.OBLIGACIONES
    elif 984 <= numero <= 999:
        return AreaJuridica.RESPONSABILIDAD_CIVIL
    elif 1000 <= numero <= 1278:
        return AreaJuridica.SUCESIONES
    elif 1279 <= numero <= 1570:
        return None
    
    return None
