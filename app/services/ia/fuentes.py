from app.models.ia.esquemas import FuenteIA
from app.services.ia.embeddings import documento_norma, huella_documento


def fuente_de_norma(norma, coincidencia=None) -> FuenteIA:
    return FuenteIA(id=norma.id, codigo=norma.codigo, numero_articulo=norma.numero_articulo,
        articulo=norma.articulo, epigrafe=norma.epigrafe, texto=norma.texto, version=norma.version,
        estado_vigencia=norma.estado_vigencia, fuente_nombre=norma.fuente_nombre,
        fuente_url=norma.fuente_url, contenido_hash=huella_documento(documento_norma(norma)),
        relevancia=coincidencia.relevancia if coincidencia else 0,
        rango_lexico=coincidencia.rango_lexico if coincidencia else None,
        rango_semantico=coincidencia.rango_semantico if coincidencia else None,
        similitud=coincidencia.similitud if coincidencia else None)
