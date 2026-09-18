from uuid import UUID
from dataclasses import asdict
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.documentos.documento import Documento
from app.models.documentos.analisis import AnalisisDocumento
from app.models.contratos.riesgo import RiesgoContractual
from app.models.shared.enums import EstadoProceso
from app.controllers.contratos.errores import DocumentoNoAnalizableError
from app.controllers.documentos.errores import DocumentoNoEncontradoError
from app.services.contratos.motor_riesgos import analizar, Analisis
from app.models.contratos.esquemas import (
    AnalisisResponse,
    ClausulaResponse,
    HallazgoResponse,
    RiesgoResponse
)

def _a_hallazgos(analisis_doc: AnalisisDocumento) -> list[HallazgoResponse]:
    hallazgos_resp = []
    for item in (analisis_doc.hallazgos or []):
        hallazgos_resp.append(HallazgoResponse(
            tipo=item["tipo"],
            texto=item["texto"],
            inicio=item["inicio"],
            fin=item["fin"],
            clausula=item.get("clausula")
        ))
    hallazgos_resp.sort(key=lambda h: h.inicio)
    return hallazgos_resp

def _a_riesgos(riesgos_models: list[RiesgoContractual]) -> list[RiesgoResponse]:
    return [
        RiesgoResponse(
            codigo_regla=r.codigo_regla,
            titulo=r.descripcion,
            severidad=r.severidad,
            articulos=r.articulos,
            explicacion=r.motivo,
            evidencia=r.evidencia,
            inicio=r.inicio,
            clausula=int(r.clausula_referencia) if r.clausula_referencia and r.clausula_referencia.isdigit() else None
        ) for r in riesgos_models
    ]

def _build_response(analisis_doc: AnalisisDocumento, documento: Documento, riesgos_models: list[RiesgoContractual]) -> AnalisisResponse:
    clausulas_resp = [
        ClausulaResponse(
            orden=c["orden"],
            encabezado=c["encabezado"],
            texto=c["texto"],
            inicio=c["inicio"],
            fin=c["fin"]
        ) for c in (analisis_doc.obligaciones or [])
    ]

    return AnalisisResponse(
        id=analisis_doc.id,
        documento_id=documento.id,
        tipo_documento=documento.tipo_documento,
        clausulas=clausulas_resp,
        hallazgos=_a_hallazgos(analisis_doc),
        parrafo_partes=(analisis_doc.partes or {}).get("parrafo"),
        riesgos=_a_riesgos(riesgos_models),
        reglas_evaluadas=analisis_doc.reglas_evaluadas,
        resumen=None,
        observaciones=None,
        creado_en=analisis_doc.creado_en
    )

def _persistir_analisis(db: Session, doc: Documento, analisis_motor: Analisis) -> AnalisisDocumento:
    partes = {
        "parrafo": analisis_motor.parrafo_partes,
        "cedulas": [asdict(h) for h in analisis_motor.hallazgos if h.tipo in ('cedula', 'nit')]
    }
    
    analisis_doc = AnalisisDocumento(
        documento_id=doc.id,
        partes=partes,
        fechas=[asdict(h) for h in analisis_motor.hallazgos if h.tipo == 'fecha'],
        montos=[asdict(h) for h in analisis_motor.hallazgos if h.tipo in ('monto_bs', 'monto_usd')],
        obligaciones=[asdict(c) for c in analisis_motor.clausulas],
        hallazgos=[asdict(h) for h in analisis_motor.hallazgos],
        reglas_evaluadas=analisis_motor.reglas_evaluadas,
        resumen=None,
        observaciones=None
    )
    db.add(analisis_doc)
    db.flush()
    return analisis_doc

def _persistir_riesgos(db: Session, analisis_id: UUID, riesgos: list) -> list[RiesgoContractual]:
    riesgos_models = []
    for riesgo in riesgos:
        r_model = RiesgoContractual(
            analisis_id=analisis_id,
            descripcion=riesgo.titulo,
            motivo=riesgo.explicacion,
            severidad=riesgo.severidad,
            clausula_referencia=str(riesgo.clausula) if riesgo.clausula is not None else None,
            codigo_regla=riesgo.codigo,
            articulos=riesgo.articulos,
            evidencia=riesgo.evidencia,
            inicio=riesgo.inicio
        )
        db.add(r_model)
        riesgos_models.append(r_model)
    return riesgos_models

def analizar_documento(db: Session, documento_id: UUID, usuario_id: UUID) -> AnalisisResponse:
    doc = db.scalar(select(Documento).where(Documento.id == documento_id, Documento.usuario_id == usuario_id))
    if not doc:
        raise DocumentoNoEncontradoError("Documento no encontrado")

    if doc.estado != EstadoProceso.COMPLETADO or not doc.texto_extraido:
        raise DocumentoNoAnalizableError("El documento no está completado o no tiene texto extraído")

    analisis_existente = db.scalar(select(AnalisisDocumento).where(AnalisisDocumento.documento_id == documento_id))
    if analisis_existente:
        riesgos_existentes = db.scalars(select(RiesgoContractual).where(RiesgoContractual.analisis_id == analisis_existente.id)).all()
        return _build_response(analisis_existente, doc, list(riesgos_existentes))

    analisis_motor = analizar(doc.texto_extraido, doc.tipo_documento)
    analisis_doc = _persistir_analisis(db, doc, analisis_motor)
    riesgos_models = _persistir_riesgos(db, analisis_doc.id, analisis_motor.riesgos)
    
    db.commit()
    db.refresh(analisis_doc)
    for rm in riesgos_models:
        db.refresh(rm)

    return _build_response(analisis_doc, doc, riesgos_models)

def obtener_analisis(db: Session, documento_id: UUID, usuario_id: UUID) -> AnalisisResponse:
    doc = db.scalar(select(Documento).where(Documento.id == documento_id, Documento.usuario_id == usuario_id))
    if not doc:
        raise DocumentoNoEncontradoError("Documento no encontrado")

    analisis_existente = db.scalar(select(AnalisisDocumento).where(AnalisisDocumento.documento_id == documento_id))
    if not analisis_existente:
        raise DocumentoNoEncontradoError("Análisis no encontrado")

    riesgos_existentes = db.scalars(select(RiesgoContractual).where(RiesgoContractual.analisis_id == analisis_existente.id)).all()
    return _build_response(analisis_existente, doc, list(riesgos_existentes))
