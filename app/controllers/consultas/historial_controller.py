from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc

from app.models.consultas.consulta import Consulta
from app.models.consultas.fuente_legal import FuenteLegal
from app.models.conocimiento.norma import Norma
from app.models.documentos.documento import Documento
from app.models.consultas.esquemas import (
    HistorialResponse, ItemHistorial, ConsultaResponse, FuenteLegalResponse
)
from app.models.shared.enums import EstadoVigencia
from app.controllers.consultas.errores import ConsultaNoEncontradaError
from app.models.ia.esquemas import RespuestaJuridicaIA

def obtener_historial(db: Session, usuario_id: UUID, limite: int = 50, desplazamiento: int = 0) -> HistorialResponse:
    subq = (
        select(FuenteLegal.consulta_id, func.count(FuenteLegal.id).label("cantidad"))
        .group_by(FuenteLegal.consulta_id)
        .subquery()
    )

    total = db.scalar(select(func.count()).select_from(Consulta).where(Consulta.usuario_id == usuario_id)) or 0

    stmt = (
        select(Consulta, func.coalesce(subq.c.cantidad, 0).label("cantidad_fuentes"),
               Documento.nombre_archivo.label("documento_nombre"))
        .outerjoin(subq, Consulta.id == subq.c.consulta_id)
        .outerjoin(Documento, Consulta.documento_id == Documento.id)
        .where(Consulta.usuario_id == usuario_id)
        .order_by(desc(Consulta.creada_en))
        .limit(limite)
        .offset(desplazamiento)
    )

    resultados = db.execute(stmt).all()
    
    items = [
        ItemHistorial(
            id=row.Consulta.id,
            texto=row.Consulta.texto,
            area_juridica=row.Consulta.area_juridica,
            cantidad_fuentes=row.cantidad_fuentes,
            documento_nombre=row.documento_nombre,
            creada_en=row.Consulta.creada_en
        )
        for row in resultados
    ]

    return HistorialResponse(total=total, items=items)

def obtener_consulta(db: Session, consulta_id: UUID, usuario_id: UUID) -> ConsultaResponse:
    consulta = db.scalar(select(Consulta).where(Consulta.id == consulta_id, Consulta.usuario_id == usuario_id))
    if not consulta:
        raise ConsultaNoEncontradaError(f"Consulta {consulta_id} no encontrada.")

    fuentes_db = db.execute(
        select(FuenteLegal, Norma)
        .outerjoin(Norma, FuenteLegal.norma_id == Norma.id)
        .where(FuenteLegal.consulta_id == consulta.id)
        .order_by(FuenteLegal.orden.asc())
    ).all()

    fuentes_responses = []
    respuesta = RespuestaJuridicaIA.model_validate_json(consulta.respuesta) if consulta.respuesta else None
    for f, norma in fuentes_db:
        # Nota: La consulta requiere datos de norma que podrian no existir si norma_id es nulo,
        # pero según la spec fuente_legal se crea siempre con norma.
        fuentes_responses.append(FuenteLegalResponse(
            norma_id=f.norma_id,
            version=norma.version if norma else None,
            utilizada=bool(respuesta and f.norma_id in respuesta.articulos_utilizados),
            articulo=f.articulo,
            numero_articulo=norma.numero_articulo if norma else 0,
            codigo=norma.codigo if norma else "",
            epigrafe=norma.epigrafe if norma else None,
            texto_citado=f.texto_citado,
            relevancia=f.relevancia,
            orden=f.orden,
            estado_vigencia=norma.estado_vigencia if norma else EstadoVigencia.SIN_VERIFICAR,
            fuente_url=norma.fuente_url if norma else ""
        ))

    documento = (db.get(Documento, consulta.documento_id)
                 if consulta.documento_id else None)

    return ConsultaResponse(
        id=consulta.id,
        texto=consulta.texto,
        documento_id=consulta.documento_id,
        # El documento se relee del modelo, no de la respuesta guardada: si lo renombraron
        # o lo borraron, el historial muestra el estado actual y no una copia vieja.
        documento_nombre=documento.nombre_archivo if documento else None,
        area_juridica=consulta.area_juridica,
        terminos_detectados=consulta.terminos_detectados,
        puntajes_por_area={}, # Historico no guarda puntajes_por_area, devolver vacio o re-calcular?
        fuentes=fuentes_responses,
        respuesta=respuesta,
        etapa_ia=consulta.etapa_ia,
        ia_error=consulta.ia_error,
        estado=consulta.estado,
        creada_en=consulta.creada_en
    )
