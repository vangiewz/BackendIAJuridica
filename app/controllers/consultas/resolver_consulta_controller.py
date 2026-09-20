from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.consultas.consulta import Consulta
from app.models.consultas.fuente_legal import FuenteLegal
from app.models.consultas.esquemas import ConsultaRequest, ConsultaResponse, FuenteLegalResponse
from app.models.contratos.riesgo import RiesgoContractual
from app.models.documentos.analisis import AnalisisDocumento
from app.models.documentos.documento import Documento
from app.models.shared.enums import EstadoProceso
from app.services.consultas.clasificador_lexico import clasificar
from app.services.consultas.intencion import Intencion, detectar, usa_documento
from app.services.conocimiento.busqueda_lexica import buscar
from app.services.consultas.diccionario_areas import VERSION_DICCIONARIO
from app.core.config import get_settings
from app.models.ia.esquemas import ContextoIA, FragmentoDocumentoIA, RespuestaJuridicaIA
from app.services.ia.consulta_documento import responder_documento, resumen_de_analisis
from app.services.ia.documento_rag import recuperar
from app.services.ia.rag import responder, abstener
from app.services.ia.ollama_client import IAError, RespuestaInvalida
from app.services.ia.metricas import pipeline, medir

# Al combinar documento y normativa el prompt tiene que dejar lugar para los artículos,
# así que del documento va un extracto y no todo lo que entraría si fuera solo.
PRESUPUESTO_DOCUMENTO_CON_NORMATIVA = 2500


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
            norma_id=norma.id,
            version=norma.version,
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


# --- Documento activo ------------------------------------------------------------

def documento_del_usuario(db: Session, documento_id: UUID | None,
                          usuario_id: UUID) -> Documento | None:
    """El documento adjunto, solo si es de quien pregunta.

    El id llega del frontend y no se le concede confianza: la consulta filtra por el
    usuario del token, así que un id ajeno simplemente no existe y la conversación
    sigue como consulta general.
    """
    if documento_id is None:
        return None
    return db.scalar(select(Documento).where(
        Documento.id == documento_id, Documento.usuario_id == usuario_id))


def _analisis_guardado(db: Session, documento_id: UUID):
    analisis = db.scalars(select(AnalisisDocumento)
        .where(AnalisisDocumento.documento_id == documento_id)
        .order_by(AnalisisDocumento.creado_en.desc()).limit(1)).first()
    if analisis is None:
        return None, []
    riesgos = list(db.scalars(select(RiesgoContractual)
        .where(RiesgoContractual.analisis_id == analisis.id)))
    return analisis, riesgos


def _respuesta_simple(texto: str, conclusion: str, documento: Documento,
                      estado: str = "fundamentada", traza=None) -> RespuestaJuridicaIA:
    return RespuestaJuridicaIA(
        estado=estado, resumen_caso=texto, contexto=ContextoIA(), conclusion=conclusion,
        documento_nombre=documento.nombre_archivo, trazabilidad=traza or {},
        limitaciones=["Acción sobre el documento; no incluye análisis normativo."])


def _guardar(texto: str, documento: Documento) -> RespuestaJuridicaIA:
    """Guardar es solo guardar: no dispara el análisis ni interpreta nada."""
    return _respuesta_simple(texto, (
        f"Documento «{documento.nombre_archivo}» guardado y activo en esta conversación. "
        "Podés preguntarme sobre su contenido, o pedirme que lo analice cuando quieras."
    ), documento, traza={"intencion": Intencion.GUARDAR_DOCUMENTO.value})


def _analizar(db: Session, texto: str, documento: Documento,
              usuario_id: UUID) -> RespuestaJuridicaIA:
    """Usa el análisis contractual existente; no reimplementa nada de él."""
    from app.controllers.contratos.analisis_controller import analizar_documento
    from app.controllers.contratos.errores import DocumentoNoAnalizableError
    try:
        analisis = analizar_documento(db, documento.id, usuario_id)
    except DocumentoNoAnalizableError as exc:
        return _respuesta_simple(texto, str(exc), documento, estado="insuficiente")

    altos = sum(1 for r in analisis.riesgos if r.severidad.value == "alta")
    partes = [f"Analicé «{documento.nombre_archivo}»."]
    if analisis.tipo_documento:
        partes.append(f"Está clasificado como {analisis.tipo_documento.value}.")
    partes.append(f"Se detectaron {len(analisis.clausulas)} cláusulas y "
                  f"{len(analisis.riesgos)} riesgos"
                  + (f", {altos} de severidad alta." if altos else "."))
    if analisis.resumen:
        partes.append(analisis.resumen)
    partes.append("Podés preguntarme por los riesgos o por cualquier cláusula.")

    respuesta = _respuesta_simple(texto, " ".join(partes), documento,
                                  traza={"intencion": Intencion.ANALIZAR_DOCUMENTO.value,
                                         "riesgos": len(analisis.riesgos)})
    respuesta.limitaciones = ["Resultado del análisis contractual del documento; "
                              "no incluye fundamento normativo."]
    return respuesta


def _sobre_documento(db: Session, texto: str, documento: Documento,
                     progreso=None) -> RespuestaJuridicaIA:
    """Pregunta contestada con el documento y nada más."""
    analisis, riesgos = _analisis_guardado(db, documento.id)
    # Si ya se analizó y preguntan por riesgos, la respuesta ya está calculada: no se
    # vuelve a ejecutar el motor ni se molesta al modelo.
    reutilizada = resumen_de_analisis(texto, documento.nombre_archivo,
                                      analisis.resumen if analisis else None, riesgos)
    if reutilizada is not None:
        return reutilizada
    return responder_documento(texto, documento.texto_extraido or "",
                               documento.nombre_archivo, progreso=progreso)


def _documento_con_normativa(db: Session, texto: str, documento: Documento,
                             progreso=None) -> RespuestaJuridicaIA:
    """Pregunta que necesita el documento Y la normativa: el RAG jurídico con contexto."""
    fragmentos = recuperar(documento.texto_extraido or "", texto,
                           presupuesto=PRESUPUESTO_DOCUMENTO_CON_NORMATIVA)
    resultado = responder(db, texto, documento={
        "NOMBRE": documento.nombre_archivo,
        "FRAGMENTOS": [{"ubicacion": f.etiqueta, "texto": f.texto} for f in fragmentos],
    }, progreso=progreso)
    resultado.documento_nombre = documento.nombre_archivo
    resultado.fuentes_documento = [
        FragmentoDocumentoIA(etiqueta=f.etiqueta, texto=f.texto) for f in fragmentos]
    return resultado


def _resolver_con_ia(db: Session, texto: str, documento: Documento | None,
                     intencion: Intencion, usuario_id: UUID, progreso) -> RespuestaJuridicaIA:
    """Elige el camino según la intención. La consulta general queda exactamente igual."""
    if documento is None or intencion == Intencion.CONSULTA_GENERAL:
        return responder(db, texto, progreso=progreso)
    if intencion == Intencion.GUARDAR_DOCUMENTO:
        return _guardar(texto, documento)
    if intencion == Intencion.ANALIZAR_DOCUMENTO:
        return _analizar(db, texto, documento, usuario_id)
    if intencion == Intencion.CONSULTA_DOCUMENTO_NORMATIVA:
        return _documento_con_normativa(db, texto, documento, progreso)
    return _sobre_documento(db, texto, documento, progreso)


@pipeline
def resolver_consulta(db: Session, request: ConsultaRequest, usuario_id: UUID,
                     consulta_existente: Consulta | None = None) -> ConsultaResponse:
    documento = documento_del_usuario(db, request.documento_id, usuario_id)
    intencion = detectar(request.texto, documento is not None)

    consulta = consulta_existente or Consulta(
        usuario_id=usuario_id,
        texto=request.texto,
        estado=EstadoProceso.PROCESANDO,
        terminos_detectados=[],
        version_diccionario=VERSION_DICCIONARIO
    )
    # La consulta queda ligada al documento solo si fue sobre él: preguntar por el Código
    # Civil con un contrato abierto sigue siendo una consulta general.
    if documento is not None and intencion != Intencion.CONSULTA_GENERAL:
        consulta.documento_id = documento.id
    db.add(consulta)
    with medir("persistence"):
        db.flush()

    clasificacion = clasificar(request.texto)
    consulta.area_juridica = clasificacion.area
    consulta.terminos_detectados = list(clasificacion.terminos_detectados)
    area_str = clasificacion.area.value if clasificacion.area else None

    respuesta = None
    fuentes_responses: list[FuenteLegalResponse] = []
    def progreso(etapa):
        consulta.etapa_ia = etapa
        with medir("progress_persistence"):
            db.commit()

    if get_settings().ia_enabled:
        try:
            respuesta = _resolver_con_ia(db, request.texto, documento, intencion,
                                         usuario_id, progreso)
        except IAError as exc:
            consulta.ia_error = str(exc)
            respuesta = abstener(request.texto, area_str,
                "error_validacion" if isinstance(exc, RespuestaInvalida) else "no_disponible", str(exc))
        for i, fuente in enumerate(respuesta.fuentes):
            db.add(FuenteLegal(consulta_id=consulta.id, norma_id=fuente.id,
                articulo=fuente.articulo, texto_citado=fuente.texto, relevancia=fuente.relevancia, orden=i))
            fuentes_responses.append(FuenteLegalResponse(norma_id=fuente.id, version=fuente.version,
                utilizada=fuente.id in respuesta.articulos_utilizados,
                articulo=fuente.articulo, numero_articulo=fuente.numero_articulo,
                codigo=fuente.codigo, epigrafe=fuente.epigrafe, texto_citado=fuente.texto,
                relevancia=fuente.relevancia, orden=i, estado_vigencia=fuente.estado_vigencia,
                fuente_url=fuente.fuente_url))
        if respuesta.estado in ("no_disponible", "error_validacion"):
            consulta.ia_error = respuesta.conclusion
            # El respaldo léxico es de normativa: no aplica cuando la pregunta era sobre
            # el documento, donde no habría nada que respaldar con artículos.
            if not fuentes_responses and not usa_documento(intencion):
                resultados = _buscar_con_respaldo(db, request.texto, area_str)
                fuentes_responses = _guardar_fuentes(db, consulta.id, resultados)
        consulta.respuesta = respuesta.model_dump_json()
    elif usa_documento(intencion) or intencion in (Intencion.ANALIZAR_DOCUMENTO,):
        # Sin IA no se puede leer el documento; guardar sí, porque no la necesita.
        respuesta = _respuesta_simple(request.texto,
            "La función de IA está desactivada, así que no puedo leer el documento ahora. "
            "El documento sigue guardado y disponible.", documento, estado="no_disponible")
        consulta.respuesta = respuesta.model_dump_json()
    elif intencion == Intencion.GUARDAR_DOCUMENTO and documento is not None:
        respuesta = _guardar(request.texto, documento)
        consulta.respuesta = respuesta.model_dump_json()
    else:
        resultados = _buscar_con_respaldo(db, request.texto, area_str)
        fuentes_responses = _guardar_fuentes(db, consulta.id, resultados)

    consulta.estado = EstadoProceso.COMPLETADO
    consulta.etapa_ia = "Completado"
    with medir("persistence"):
        db.commit()
        db.refresh(consulta)

    return ConsultaResponse(
        id=consulta.id,
        texto=consulta.texto,
        documento_id=consulta.documento_id,
        documento_nombre=documento.nombre_archivo if documento else None,
        intencion=intencion.value,
        area_juridica=consulta.area_juridica,
        terminos_detectados=consulta.terminos_detectados,
        puntajes_por_area=clasificacion.puntajes_por_area,
        fuentes=fuentes_responses,
        respuesta=respuesta,
        etapa_ia=consulta.etapa_ia,
        ia_error=consulta.ia_error,
        estado=consulta.estado,
        creada_en=consulta.creada_en
    )
