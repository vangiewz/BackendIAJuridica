import hashlib
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.models.conocimiento.norma import Norma
from app.models.conocimiento.esquemas import VersionCorpus, PaginaCorpus, ArticuloCorpus, Ubicacion

def huella_corpus(db: Session, codigo: str) -> VersionCorpus | None:
    """Identifica el estado del corpus sin mandarlo entero.

    Se calcula con sha256 truncado a 16 sobre cantidad de normas activas, el maximo
    `creada_en` y el maximo `version`. Cualquier alta, baja o reingesta la mueve.
    """
    stats = db.execute(
        select(
            func.count(Norma.id),
            func.max(Norma.creada_en),
            func.max(Norma.version)
        ).where(Norma.codigo == codigo, Norma.activa.is_(True))
    ).first()

    if not stats or stats[0] == 0:
        return None

    cantidad = stats[0]
    max_creada_en = stats[1]
    max_version = stats[2]

    m = hashlib.sha256()
    m.update(str(cantidad).encode('utf-8'))
    m.update(str(max_creada_en.timestamp() if max_creada_en else 0).encode('utf-8'))
    m.update(str(max_version).encode('utf-8'))
    
    huella = m.hexdigest()[:16]

    return VersionCorpus(
        codigo=codigo,
        version=huella,
        cantidad=cantidad,
        generada_en=max_creada_en
    )

def pagina_corpus(db: Session, codigo: str, desde: int, limite: int) -> PaginaCorpus | None:
    """Articulos activos ordenados por `numero_articulo` ascendente."""
    version_info = huella_corpus(db, codigo)
    if not version_info:
        return None
        
    stmt = select(
        Norma.id, Norma.codigo, Norma.articulo, Norma.numero_articulo,
        Norma.epigrafe, Norma.texto, Norma.area_juridica, Norma.libro, Norma.parte,
        Norma.titulo, Norma.capitulo, Norma.seccion, Norma.estado_vigencia,
        Norma.nota_vigencia, Norma.fuente_nombre, Norma.fuente_url, Norma.version
    ).where(Norma.codigo == codigo, Norma.activa.is_(True))\
     .order_by(Norma.numero_articulo.asc()).offset(desde).limit(limite)
    
    articulos = []
    for fila in db.execute(stmt).all():
        ubicacion = Ubicacion(
            libro=fila.libro, parte=fila.parte, titulo=fila.titulo,
            capitulo=fila.capitulo, seccion=fila.seccion
        )
        art = ArticuloCorpus(
            id=fila.id, codigo=fila.codigo, articulo=fila.articulo,
            numero_articulo=fila.numero_articulo, epigrafe=fila.epigrafe,
            texto=fila.texto, area_juridica=fila.area_juridica,
            ubicacion=ubicacion, estado_vigencia=fila.estado_vigencia,
            nota_vigencia=fila.nota_vigencia, fuente_nombre=fila.fuente_nombre,
            fuente_url=fila.fuente_url, version=fila.version
        )
        articulos.append(art)
        
    return PaginaCorpus(
        codigo=codigo, version=version_info.version, total=version_info.cantidad,
        desde=desde, articulos=articulos
    )
