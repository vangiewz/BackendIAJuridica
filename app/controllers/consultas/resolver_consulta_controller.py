from uuid import UUID
from sqlalchemy.orm import Session
from app.models.consultas.consulta import Consulta
from app.models.consultas.fuente_legal import FuenteLegal
from app.models.consultas.esquemas import ConsultaRequest, ConsultaResponse, FuenteLegalResponse
from app.models.shared.enums import EstadoProceso
from app.services.consultas.clasificador_lexico import clasificar
from app.services.conocimiento.busqueda_lexica import buscar
from app.services.consultas.diccionario_areas import VERSION_DICCIONARIO

def _buscar_con_respaldo(db: Session, texto: str, area_str: str | None) -> list:
    total, resultados = buscar(db, texto, area=area_str, limite=10)
    if area_str and len(resultados) == 0:
        total, resultados = buscar(db, texto, area=None, limite=10)
    return resultados

def _guardar_fuentes(db: Session, consulta_id: UUID, resultados: list) -> list[FuenteLegalResponse]:
    fuentes_responses = []
    for i, row in enumerate(resultados):
        norma = row.Norma
        relevancia = row.relevancia

        fuente = FuenteLegal(
            consulta_id=consulta_id,
            norma_id=norma.id,
            articulo=norma.articulo,
            texto_citado=norma.texto,
            relevancia=relevancia,
            orden=i
        )
        db.add(fuente)

        fuentes_responses.append(FuenteLegalResponse(
            articulo=norma.articulo,
            numero_articulo=norma.numero_articulo,
            codigo=norma.codigo,
            epigrafe=norma.epigrafe,
            texto_citado=norma.texto,
            relevancia=relevancia,
            orden=i,
            estado_vigencia=norma.estado_vigencia,
            fuente_url=norma.fuente_url
        ))
    return fuentes_responses

def resolver_consulta(db: Session, request: ConsultaRequest, usuario_id: UUID) -> ConsultaResponse:
    consulta = Consulta(
        usuario_id=usuario_id,
        texto=request.texto,
        estado=EstadoProceso.PROCESANDO,
        terminos_detectados=[],
        version_diccionario=VERSION_DICCIONARIO
    )
    db.add(consulta)
    db.flush()

    clasificacion = clasificar(request.texto)
    consulta.area_juridica = clasificacion.area
    consulta.terminos_detectados = list(clasificacion.terminos_detectados)
    area_str = clasificacion.area.value if clasificacion.area else None

    resultados = _buscar_con_respaldo(db, request.texto, area_str)
    fuentes_responses = _guardar_fuentes(db, consulta.id, resultados)

    consulta.estado = EstadoProceso.COMPLETADO
    db.commit()
    db.refresh(consulta)

    return ConsultaResponse(
        id=consulta.id,
        texto=consulta.texto,
        area_juridica=consulta.area_juridica,
        terminos_detectados=consulta.terminos_detectados,
        puntajes_por_area=clasificacion.puntajes_por_area,
        fuentes=fuentes_responses,
        respuesta=None,
        estado=consulta.estado,
        creada_en=consulta.creada_en
    )
