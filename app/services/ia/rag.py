import json
import logging
import os
import re
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select
from app.models.conocimiento.norma import Norma
from time import perf_counter
from app.core.config import get_settings
from app.models.ia.esquemas import (RespuestaModelo, RespuestaSeleccion, RespuestaJuridicaIA,
                                    FundamentoIA, ContextoIA, DescomposicionModelo,
                                    RespuestaCasoComplejo, RevisionModelo)
from app.services.ia.casos import (ProblemaDetectado, es_caso_complejo, hechos_literales,
                                   problemas_por_catalogo, problemas_de_preguntas,
                                   tema_de_pregunta, datos_estructurados,
                                   hechos_estructurados, derivaciones_verificadas)
from app.services.ia.fragmentos import resolver_citas, resolver_citas_complejo
from app.services.ia.rag_simple import generar_simple
from app.services.conocimiento.busqueda_hibrida import buscar_hibrida, buscar_por_problemas
from app.services.consultas.clasificador_lexico import clasificar
from app.services.ia.fuentes import fuente_de_norma
from app.services.ia.ollama_client import OllamaClient, IAError, RespuestaInvalida
from app.services.ia.prompts import (CORRECCIONES, construir_prompt, SISTEMA_CONTEXTO,
                                     VERSION_PROMPT, CONTEXTO_INTEGRADO,
                                     SISTEMA_DESCOMPOSICION, SISTEMA_REVISION)
from app.services.ia.metricas import medir, pipeline, rechazo, sumar
from app.services.ia.validacion import (validar_citas, validar_contexto, depurar_contexto,
                                         solicitud_no_fundamentable, validar_caso_complejo,
                                         depurar_limitaciones, verificar_prosa, renderizar_hechos)
from app.services.shared.normalizacion import normalizar

logger = logging.getLogger(__name__)
INSUFICIENTE = "No se encontró suficiente fundamento en las fuentes jurídicas disponibles para responder esta consulta con seguridad."
NOTA = "Respuesta generada como herramienta de apoyo a partir de las fuentes jurídicas indicadas."
NO_VALIDADA = ("La redacción generada no pudo verificarse contra las fuentes recuperadas, "
               "así que no se muestra. Estas son las normas encontradas para el caso.")


def _guardar_rechazo_complejo(generado, exc, fuentes, intento, por_problema=None):
    """Diagnóstico local opt-in; nunca va en la respuesta ni en la traza pública."""
    directorio = os.environ.get("IA_DEBUG_RECHAZOS_DIR")
    salida_original = (generado.model_dump(mode="json") if generado is not None else
                       getattr(exc, "salida_estructurada_original", None))
    if not directorio or salida_original is None:
        return None
    fuente_id = getattr(exc, "fuente", None)
    fuente = next((f for i, f in enumerate(fuentes, 1) if f"F{i}" == fuente_id), None)
    indice = getattr(exc, "indice_apartado", None)
    apartados = getattr(generado, "analisis", [])
    apartado = (apartados[indice] if isinstance(indice, int)
               and 0 <= indice < len(apartados) else None)
    pregunta_id = (getattr(apartado, "pregunta_id", None) if apartado else
                   getattr(exc, "apartado", None))
    registro = {
        "intento": intento,
        "salida_estructurada_original": salida_original,
        "fallo": {
            "pregunta_id": pregunta_id,
            "apartado": getattr(exc, "apartado", None),
            "indice_apartado": getattr(exc, "indice_apartado", None),
            "hechos_usados": getattr(apartado, "hechos_usados", []) if apartado else [],
            "fuente_ids": (por_problema or {}).get(pregunta_id, []),
            "texto": getattr(exc, "texto", salida_original if isinstance(salida_original, str) else None),
            "regla": exc.motivo,
            "valor_ofensivo": exc.detalle,
            "fuente": ({"id_prompt": fuente_id, "norma_id": str(fuente.id),
                        "articulo": fuente.numero_articulo} if fuente else None),
            "cita_ids": getattr(exc, "cita_ids", []),
            "cita_textual": getattr(exc, "cita", None),
        },
    }
    try:
        ruta = Path(directorio)
        ruta.mkdir(parents=True, exist_ok=True)
        archivo = ruta / f"rechazo-{uuid4().hex}.json"
        with archivo.open("x", encoding="utf-8") as salida:
            json.dump(registro, salida, ensure_ascii=False, indent=2)
        return archivo
    except OSError:
        logger.warning("No se pudo guardar el diagnóstico local de rechazo complejo")
        return None


def es_relato_de_hechos(pregunta: str) -> bool:
    """Activa la extraccion de hechos solo cuando se describe una situacion."""
    plano = normalizar(pregunta)
    if re.search(r"\b(?:que pasa si|que ocurre si|en caso de que|supongamos que)\b", plano):
        return False
    return bool(re.search(
        r"\b(?:mi|mis|me|nos|nuestro|nuestra|yo)\b.{0,100}"
        r"\b(?:paga|pago|pague|compre|vendi|debe|deben|incumplio|firmo|firme|"
        r"entrego|entregue|preste|alquilo|fallecio|reclama|demanda|demando|niega)\b"
        r"|\b(?:tengo|tenemos)\b.{0,60}\b(?:contrato|deuda|problema)\b"
        r"|\b(?:compre|pague|vendi|preste|firme|alquile|recibi)\b", plano))


def abstener(pregunta, area=None, estado="insuficiente", mensaje=INSUFICIENTE, fuentes=None,
             traza=None, contexto=None):
    # La abstención conserva el contexto interpretado: no hay fundamento, pero sí comprensión.
    return RespuestaJuridicaIA(estado=estado, resumen_caso=pregunta, area_juridica=area,
        contexto=ContextoIA.model_validate(contexto or {}),
        conclusion=mensaje, fuentes=fuentes or [], limitaciones=[NOTA], trazabilidad=traza or {})


def interpretar_contexto(relato, client=None, traza=None) -> ContextoIA:
    """HU-02: estructura el relato del usuario. Es auxiliar: toda afirmación debe constar
    literalmente en el relato, y si no puede validarse se continúa sin contexto."""
    client = client or OllamaClient()
    messages = [{"role": "system", "content": SISTEMA_CONTEXTO},
                {"role": "user", "content": json.dumps({"RELATO": relato}, ensure_ascii=False)}]
    tick = perf_counter()
    contexto = ContextoIA()
    try:
        contexto = validar_contexto(client.generar(messages, ContextoIA, intentos=1), relato)
    except RespuestaInvalida as exc:
        if traza is not None:
            traza["contexto_motivo"] = exc.motivo
    except IAError:
        if traza is not None:
            traza["contexto_motivo"] = "ia_no_disponible"
    if traza is not None:
        traza["contexto_ms"] = round((perf_counter() - tick) * 1000, 2)
    return contexto


def generar_con_fuentes(pregunta, fuentes, area=None, contexto=None, documento=None,
                        tarea=None, client=None, integrar_contexto=False, progreso=None):
    client = client or OllamaClient()
    try:
        with medir("prompt_build"):
            messages, used = construir_prompt(pregunta, fuentes, contexto, documento, tarea,
                                              citas_identificadas=True)
            if integrar_contexto:
                messages[0]["content"] += CONTEXTO_INTEGRADO
            else:
                # Sin relato no hay hechos que extraer, pero el análisis jurídico se
                # desarrolla igual. Antes acá se pedía "una frase muy corta" y "hasta dos
                # fundamentos": eso recortaba por rendimiento respuestas que merecían
                # desarrollo, y es justo lo que hacía parecer superficial al sistema.
                messages[0]["content"] += (
                    "\nConsulta general sin relato: contexto debe tener listas vacias. "
                    "El análisis, la conclusión y los fundamentos se desarrollan con "
                    "normalidad, tantos como cuestiones plantee la consulta.")
    except ValueError:
        return abstener(pregunta, area, mensaje=INSUFICIENTE + " El documento o contexto excede el límite de esta función.")
    trace = {"prompt_version": VERSION_PROMPT, "modelo": client.settings.ollama_model,
             "fuentes_enviadas": [str(f.id) for f in used],
             "fuentes_omitidas_por_presupuesto": len(fuentes)-len(used)}
    if not used:
        return abstener(pregunta, area, traza=trace, contexto=contexto)
    tick = perf_counter()
    for attempt in range(2):
        if attempt:
            sumar("retry_count", 1)
            if progreso:
                progreso("Generando respuesta...")
        attempt_started = perf_counter()
        try:
            generated = client.generar(messages, RespuestaSeleccion, intentos=1)
            if progreso:
                progreso("Validando respuesta...")
            if integrar_contexto:
                with medir("context_validation"):
                    # Un hecho reformulado solo se pierde a sí mismo: lo que el modelo
                    # sí copió literalmente del relato sigue siendo verificable y se usa.
                    contexto, descartes = depurar_contexto(generated.contexto, pregunta)
                if descartes:
                    trace["contexto_descartes"] = descartes
                    for motivo in descartes:
                        rechazo(motivo)
            with medir("pydantic"):
                generated = resolver_citas(generated, used)
            with medir("citation_validation"):
                allowed = validar_citas(generated, used, pregunta)
            trace["llm_ms"] = round((perf_counter()-tick)*1000, 2)
            trace["intentos_validacion"] = attempt+1
            trace["ollama"] = client.last_metrics
            if not generated.suficiente:
                return abstener(pregunta, area, fuentes=used, traza=trace, contexto=contexto)
            grounds = [FundamentoIA(norma_id=allowed[a.fuente].id,
                cita_textual=a.cita, explicacion=a.explicacion) for a in generated.analisis]
            return RespuestaJuridicaIA(estado="fundamentada", resumen_caso=generated.resumen,
                area_juridica=area, contexto=ContextoIA.model_validate(contexto or {}),
                analisis=grounds, conclusion=generated.conclusion,
                articulos_utilizados=list(dict.fromkeys(a.norma_id for a in grounds)),
                fuentes=used, limitaciones=[*generated.limitaciones, NOTA,
                    "La vigencia es la registrada en cada fuente; no fue determinada por el modelo."], trazabilidad=trace)
        except RespuestaInvalida as exc:
            rechazo(exc.motivo)
            trace["validacion_motivo"] = exc.motivo
            trace["intentos_validacion"] = attempt+1
            concreto = f" Lo que sobra es «{exc.detalle}»: quítalo o reescribe esa frase sin él." if getattr(exc, "detalle", "") else ""
            messages = [messages[0], messages[1], {"role": "user", "content":
                "Corrección del sistema: " + CORRECCIONES.get(exc.motivo, CORRECCIONES["no_especificado"]) +
                concreto + " Si no puedes cumplir, responde suficiente=false y analisis=[]."}]
        finally:
            if attempt:
                sumar("retry_ms", (perf_counter()-attempt_started)*1000)
    # Agotados los intentos no se muestra nada sin verificar, pero sí las fuentes
    # recuperadas: el usuario conserva la normativa aunque falte la redacción.
    return abstener(pregunta, area, "error_validacion", NO_VALIDADA, used, trace, contexto)


def descomponer_caso(relato, client, traza) -> list[ProblemaDetectado]:
    """Primera llamada: qué cuestiones jurídicas distintas plantea el caso.

    De acá solo salen títulos y términos de búsqueda. Ninguna garantía depende de esto:
    las normas se recuperan del corpus y las citas siguen validándose igual. Si el modelo
    falla, el catálogo determinista cubre el caso y el flujo continúa.
    """
    tick = perf_counter()
    preguntas = problemas_de_preguntas(relato)
    if preguntas:
        traza["descomposicion"] = "preguntas_explicitas"
        traza["preguntas_usuario"] = [p.pregunta for p in preguntas]
        traza["descomposicion_ms"] = round((perf_counter() - tick) * 1000, 2)
        traza["problemas"] = [p.titulo for p in preguntas]
        return preguntas
    mensajes = [{"role": "system", "content": SISTEMA_DESCOMPOSICION},
                {"role": "user", "content": json.dumps({"RELATO": relato}, ensure_ascii=False)}]
    detectados: list[ProblemaDetectado] = []
    try:
        propuesta = client.generar(mensajes, DescomposicionModelo, intentos=2)
        detectados = [ProblemaDetectado(clave=f"p{i}", titulo=p.titulo, consulta=p.consulta,
                       familia=(tema[0] if (tema := tema_de_pregunta(p.titulo + ' ' + p.consulta)) else ""))
                      for i, p in enumerate(propuesta.problemas, 1)]
    except IAError as exc:
        traza["descomposicion_motivo"] = getattr(exc, "motivo", "ia_no_disponible")
    modelo_sugirio = bool(detectados)
    obligatorios = problemas_por_catalogo(relato)
    presentes = {p.familia for p in detectados}
    for problema in obligatorios:
        tema = tema_de_pregunta(problema.titulo)
        familia = tema[0] if tema else problema.clave
        if familia not in presentes:
            detectados.append(ProblemaDetectado(problema.clave, problema.titulo,
                                                problema.consulta, familia=familia))
            presentes.add(familia)
    if not modelo_sugirio:
        traza["descomposicion"] = "catalogo"
    traza["descomposicion_ms"] = round((perf_counter() - tick) * 1000, 2)
    traza["problemas"] = [p.titulo for p in detectados]
    return detectados


# El revisor corre con la ventana de contexto normal (4096), no con la ampliada del
# análisis. Ocho explicaciones completas más el relato no entran, y Ollama recortaría el
# prompt en silencio. Para juzgar cobertura y contradicciones alcanza el comienzo de cada
# apartado; la validación de citas y cifras ya se hizo sobre el texto completo.
EXTRACTO_REVISION = 450


def _revisar(relato, problemas, generado, limitaciones, client, traza, titulos=None):
    """Segunda mirada sobre la respuesta: qué quedó sin tratar y qué limitación sobra.

    No reescribe nada. Devuelve (limitaciones depuradas, problemas omitidos); quitar
    texto no puede inventar nada, así que esta pasada no toca ninguna garantía.
    `titulos` traduce el id de problema que devuelve el modelo (p1, p2...) a su título,
    que es lo que el revisor ve en PROBLEMAS: sin eso comparaba ids contra títulos.
    """
    titulos = titulos or {}
    tick = perf_counter()
    cuerpo = {"PREGUNTA": relato,
              "PROBLEMAS": [titulos.get(p.clave, p.titulo) for p in problemas],
              "APARTADOS": [{"problema": titulos.get(a.problema, a.problema),
                             "extracto": a.explicacion[:EXTRACTO_REVISION]}
                            for a in generado.analisis],
              "LIMITACIONES": limitaciones}
    mensajes = [{"role": "system", "content": SISTEMA_REVISION},
                {"role": "user", "content": json.dumps(cuerpo, ensure_ascii=False)}]
    try:
        revision = client.generar(mensajes, RevisionModelo, intentos=1)
    except IAError:
        traza["revision"] = "no_disponible"
        return limitaciones, []
    sobrantes = {i for i in revision.limitaciones_irrelevantes if 0 <= i < len(limitaciones)}
    depuradas = [l for i, l in enumerate(limitaciones) if i not in sobrantes]
    traza["revision_ms"] = round((perf_counter() - tick) * 1000, 2)
    traza["revision_coherente"] = revision.coherente
    if sobrantes:
        traza["limitaciones_descartadas_revision"] = len(sobrantes)
    tratados = {normalizar(titulos.get(a.problema, a.problema)) for a in generado.analisis}
    omitidos = [t for t in revision.problemas_omitidos if normalizar(t) not in tratados]
    if omitidos:
        traza["problemas_omitidos"] = omitidos
    return depuradas, omitidos


def _titulo_seguro(titulo, fuentes, relato, numero):
    """El título del problema, salvo que mencione algo que no consta en fuentes o relato."""
    try:
        verificar_prosa(titulo, fuentes, relato, permitir_derivadas=True)
        return titulo
    except RespuestaInvalida:
        return f"Cuestión {numero}"


def responder_caso_complejo(db, relato, area, client, progreso, traza):
    """Flujo profundo: descomponer, buscar por problema, redactar y revisar.

    Son varias llamadas a propósito. Una sola pasada obligaba a comprimir el caso entero
    en un formato corto, y un caso con mora, cláusula penal, vicios y resolución no cabe
    ahí sin perder la mitad.
    """
    if progreso:
        progreso("Identificando los problemas jurídicos...")
    problemas = descomponer_caso(relato, client, traza)
    if not problemas:
        return None

    if progreso:
        progreso(f"Buscando normativa para {len(problemas)} cuestiones...")
    with medir("retrieval_total"):
        # La clasificación global de área no puede ocultar las fuentes de otro tema.
        retrieval = buscar_por_problemas(db, problemas, area=None, client=client)
    traza.update({"retrieval": retrieval.modo, **retrieval.tiempos_ms,
                  "fuentes_por_problema": retrieval.por_problema})
    fuentes = [fuente_de_norma(fila.Norma, fila) for fila in retrieval.resultados]
    if not fuentes:
        return abstener(relato, area, mensaje="No encontré fuentes pertinentes para los problemas de este caso.",
                        traza={**traza, "modo": "caso_complejo"},
                        contexto=ContextoIA(hechos=hechos_literales(relato)))
    # Las fuentes ya son objetos desligados de la sesión y la generación no vuelve a
    # tocar la base. Dejar abierta la transacción de lectura durante los minutos que
    # tarda el modelo hace que el proveedor corte la conexión por inactividad y la
    # respuesta se pierda entera al intentar cerrarla.
    db.commit()

    hechos = hechos_literales(relato)
    datos_caso = datos_estructurados(relato)
    hechos_caso = hechos_estructurados(relato)
    derivaciones = derivaciones_verificadas(hechos_caso)
    traza["datos_verificados"] = {clave: valor["valor"] for clave, valor in datos_caso.items()}
    traza["hechos_verificados"] = {clave: {"tipo": valor["tipo"], "valor": valor["valor"]}
                                  for clave, valor in hechos_caso.items()}
    contexto = ContextoIA(hechos=hechos)
    if progreso:
        progreso(f"Analizando el caso con {len(fuentes)} fuentes...")
    with medir("prompt_build"):
        mensajes, usadas = construir_prompt(relato, fuentes, contexto=None,
                                            citas_identificadas=True, problemas=problemas,
                                            por_problema=retrieval.por_problema,
                                            hechos_caso=hechos_caso, derivaciones=derivaciones)
    traza["fuentes_enviadas"] = [str(f.id) for f in usadas]

    # El modelo devuelve el id del problema (p1, p2...). El título viene de otra llamada
    # del modelo y termina a la vista del usuario: se comprueba como cualquier otro texto
    # y, si nombra un artículo o una cifra que no consta, se reemplaza por uno neutro.
    titulos = {p.clave: _titulo_seguro(p.titulo, usadas, relato, n)
               for n, p in enumerate(problemas, 1)}

    tick = perf_counter()
    for intento in range(2):
        if intento:
            sumar("retry_count", 1)
        generado = None
        try:
            generado = client.generar(mensajes, RespuestaCasoComplejo, intentos=1)
            if not generado.resumen.strip() or not generado.conclusion.strip():
                raise RespuestaInvalida("resumen_o_conclusion_ausente")
            if progreso:
                progreso("Validando fundamentos...")
            with medir("pydantic"):
                items = resolver_citas_complejo(generado, usadas)
            limitaciones, descartadas = depurar_limitaciones(generado.limitaciones, relato)
            if descartadas:
                traza["limitaciones_contradictorias"] = descartadas
            with medir("citation_validation"):
                permitidas = validar_caso_complejo(
                    items, generado.resumen, generado.conclusion,
                    [*limitaciones, *(a.explicacion for a in generado.analisis if not a.citas)],
                    usadas, relato, por_problema=retrieval.por_problema,
                    problemas=problemas, apartados=generado.analisis,
                    hechos=hechos_caso, derivaciones=derivaciones)
            # La revisión libre que devolvía coherent=false sin acciones se retira del
            # camino normal. Cobertura, citas, cifras y hechos se revisan por apartado.
            traza["revision"] = "determinista_por_apartado"
            traza.update({"llm_ms": round((perf_counter() - tick) * 1000, 2),
                          "intentos_validacion": intento + 1, "ollama": client.last_metrics,
                          "modo": "caso_complejo", "problemas_analizados": len(generado.analisis)})
            sin_citas = [a for a in generado.analisis if not a.citas]
            if sin_citas:
                traza["problemas_sin_fuentes"] = [titulos.get(a.problema, a.problema) for a in sin_citas]
            if not items:
                return abstener(relato, area, fuentes=usadas, traza=traza, contexto=contexto)
            # Una explicación por apartado: si un apartado se apoya en tres artículos, la
            # explicación acompaña al primero y los otros solo aportan su cita.
            fundamentos, ya_explicados = [], set()
            for i in items:
                primera = i["apartado"] not in ya_explicados
                ya_explicados.add(i["apartado"])
                fundamentos.append(FundamentoIA(
                    problema=titulos.get(i["problema"], i["problema"]),
                    norma_id=permitidas[i["fuente"]].id, cita_textual=i["cita"],
                    explicacion=renderizar_hechos(i["explicacion"], hechos_caso, derivaciones)
                    if primera else ""))
            for apartado in sin_citas:
                fundamentos.append(FundamentoIA(
                    problema=titulos.get(apartado.problema, apartado.problema),
                    norma_id=None, cita_textual="",
                    explicacion=renderizar_hechos(apartado.explicacion, hechos_caso, derivaciones)))
            return RespuestaJuridicaIA(
                estado="fundamentada", resumen_caso=renderizar_hechos(generado.resumen, hechos_caso, derivaciones),
                area_juridica=area, contexto=contexto, analisis=fundamentos,
                conclusion=renderizar_hechos(generado.conclusion, hechos_caso, derivaciones),
                articulos_utilizados=list(dict.fromkeys(f.norma_id for f in fundamentos if f.norma_id)),
                fuentes=usadas, limitaciones=[renderizar_hechos(l, hechos_caso, derivaciones)
                                             for l in limitaciones],
                trazabilidad=traza)
        except RespuestaInvalida as exc:
            _guardar_rechazo_complejo(generado, exc, usadas, intento + 1,
                                     retrieval.por_problema)
            rechazo(exc.motivo)
            traza["validacion_motivo"] = exc.motivo
            if getattr(exc, "detalle", ""):
                # Qué disparó el rechazo: sin esto una respuesta descartada no dejaba
                # forma de saber si el modelo inventó algo o si falló la comprobación.
                traza["validacion_detalle"] = exc.detalle
            traza["intentos_validacion"] = intento + 1
            concreto = f" Lo que sobra es «{exc.detalle}»: quítalo o reescribe esa frase sin él." if getattr(exc, "detalle", "") else ""
            mensajes = [mensajes[0], mensajes[1], {"role": "user", "content":
                "Corrección del sistema: " + CORRECCIONES.get(exc.motivo, CORRECCIONES["no_especificado"]) +
                concreto +
                " Mantén todos los problemas; si uno no puede fundamentarse, deja citas=[] y explícalo."}]
        except IAError as exc:
            traza["caso_complejo_fallo"] = getattr(exc, "motivo", type(exc).__name__)
            logger.warning("caso complejo no completado: %s", traza["caso_complejo_fallo"])
            return abstener(relato, area, "no_disponible", str(exc), usadas, traza, contexto)
    return abstener(relato, area, "error_validacion", NO_VALIDADA, usadas, traza, contexto)


@pipeline
def responder(db, pregunta, contexto=None, documento=None, progreso=None):
    started = perf_counter()
    with medir("classification"):
        signal = clasificar(pregunta)
    area = signal.area.value if signal.area else None
    if solicitud_no_fundamentable(pregunta):
        return abstener(pregunta, area)
    numeros_solicitados = {int(n) for n in re.findall(r"\bart[íi]culo\s+(\d+)", pregunta, re.I)}
    if numeros_solicitados:
        existentes = set(db.scalars(select(Norma.numero_articulo).where(
            Norma.activa.is_(True), Norma.numero_articulo.in_(numeros_solicitados))))
        if numeros_solicitados - existentes:
            return abstener(pregunta, area)
    simple = get_settings().ia_pipeline == "simple"
    # El diccionario de áreas no cubre todo el vocabulario civil: «¿qué diferencia hay
    # entre mora e incumplimiento?» no disparaba ningún término y se rechazaba antes de
    # buscar nada. En el modo simple decide la recuperación, que es quien de verdad sabe
    # si hay normas pertinentes; si no las hay, más abajo se abstiene igual.
    if (not simple and not area and not signal.terminos_detectados and not documento
            and not es_caso_complejo(pregunta)):
        return abstener(pregunta, area, mensaje=INSUFICIENTE + " Describa los hechos y la relación civil implicada.")
    traza_previa = {}
    # Un caso con varias cuestiones va por el recorrido profundo: descomponer, buscar por
    # problema y redactar sin comprimir. Si ese camino no puede completarse (sin problemas
    # detectados, sin fuentes o sin IA) se cae al flujo normal, que sigue igual que antes.
    if not simple and documento is None and contexto is None and es_caso_complejo(pregunta):
        profundo = responder_caso_complejo(db, pregunta, area, OllamaClient(), progreso,
                                           dict(traza_previa))
        profundo.trazabilidad["total_ms"] = round((perf_counter() - started) * 1000, 2)
        return profundo

    # Retrieval siempre dependió del relato original, nunca del contexto de HU-02.
    # Ahora el contexto se obtiene en la misma llamada que redacta la respuesta.
    if progreso:
        progreso("Buscando normativa...")
    with medir("retrieval_total"):
        retrieval = buscar_hibrida(db, pregunta, limite=6 if simple else None)
    fuentes = [fuente_de_norma(row.Norma, row) for row in retrieval.resultados]
    modo_consulta = "relato" if es_relato_de_hechos(pregunta) else "general"
    if progreso:
        progreso("Analizando fuentes...")
    if retrieval.advertencia and not fuentes:
        return abstener(pregunta, area, "no_disponible", retrieval.advertencia, fuentes,
                        {**traza_previa, "retrieval": retrieval.modo, **retrieval.tiempos_ms}, contexto)
    if not fuentes:
        return abstener(pregunta, area,
            mensaje="No encontré fuentes suficientemente pertinentes para responder esta consulta con seguridad.",
            traza={"modo_consulta": modo_consulta, "retrieval": retrieval.modo,
                   **retrieval.tiempos_ms})
    if progreso:
        progreso("Generando respuesta...")
    if simple:
        result = generar_simple(pregunta, fuentes, area, documento, progreso)
    else:
        result = generar_con_fuentes(pregunta, fuentes, area, contexto, documento,
            integrar_contexto=contexto is None and modo_consulta == "relato", progreso=progreso)
    result.trazabilidad.update({**traza_previa, "retrieval": retrieval.modo, **retrieval.tiempos_ms,
                               "retrieval_advertencia": retrieval.advertencia,
                               "modo_consulta": modo_consulta,
                               "total_ms": round((perf_counter()-started)*1000, 2)})
    if get_settings().environment == "development":
        logger.info("rag estado=%s fuentes=%d total_ms=%.1f", result.estado, len(result.fuentes),
                    result.trazabilidad["total_ms"])
    return result
