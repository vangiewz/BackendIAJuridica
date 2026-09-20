"""HU-10: resumen y observaciones de IA sobre un contrato ya analizado por reglas.

El motor determinista sigue siendo el que detecta riesgos. Aquí el modelo solo redacta
sobre lo que se le entrega: cláusulas del documento, riesgos ya detectados y normativa
recuperada. Toda observación debe citar un fragmento literal del contrato, de modo que
nunca pueda presentarse como riesgo algo que las reglas no encontraron.
"""
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.conocimiento.norma import Norma
from app.models.ia.esquemas import AnalisisContratoIA, AnalisisContratoModelo, ObservacionIA
from app.services.conocimiento.busqueda_hibrida import buscar_hibrida
from app.services.ia.fuentes import fuente_de_norma
from app.services.ia.ollama_client import IAError, OllamaClient, RespuestaInvalida
from app.services.ia.prompts import TAREA_CONTRATO, construir_prompt
from app.services.ia.validacion import validar_observaciones
from app.services.ia.metricas import medir, pipeline, sumar, rechazo

MAX_CLAUSULAS = 12
MAX_TEXTO_CLAUSULA = 400


def _fuentes_del_contrato(db: Session, tipo: str, riesgos, clausulas):
    """Primero los artículos que ya citan las reglas; el resto se completa por búsqueda."""
    articulos = list(dict.fromkeys(n for riesgo in riesgos for n in (riesgo.articulos or [])))
    fuentes = []
    if articulos:
        normas = db.scalars(select(Norma).where(
            Norma.activa.is_(True), Norma.numero_articulo.in_(articulos))).all()
        orden = {numero: i for i, numero in enumerate(articulos)}
        fuentes = [fuente_de_norma(n) for n in sorted(normas, key=lambda n: orden[n.numero_articulo])]
    limite = get_settings().rag_top_k
    if len(fuentes) < limite:
        consulta = ' '.join([tipo.replace('_', ' ')] + [c.get("encabezado", "") for c in clausulas[:6]])
        recuperados = buscar_hibrida(db, consulta, limite=limite)
        presentes = {f.id for f in fuentes}
        for fila in recuperados.resultados:
            if fila.Norma.id not in presentes and len(fuentes) < limite:
                fuentes.append(fuente_de_norma(fila.Norma, fila))
    return fuentes[:limite]


def _documento_para_prompt(tipo, texto, clausulas, hallazgos, riesgos):
    return {
        "TIPO_DE_CONTRATO": tipo,
        "CLAUSULAS": [{"orden": c.get("orden"), "encabezado": c.get("encabezado", ""),
                       "texto": (c.get("texto") or "")[:MAX_TEXTO_CLAUSULA]}
                      for c in clausulas[:MAX_CLAUSULAS]],
        "DATOS_EXTRAIDOS": [{"tipo": h.get("tipo"), "texto": h.get("texto")}
                            for h in hallazgos if h.get("tipo") in
                            ("fecha", "monto_bs", "monto_usd", "cedula", "nit")][:20],
        # Los riesgos llegan ya resueltos por reglas: el modelo los describe, no los decide.
        "RIESGOS_YA_DETECTADOS_POR_REGLAS": [
            {"codigo": r.codigo_regla, "titulo": r.descripcion,
             "severidad": getattr(r.severidad, "value", r.severidad),
             "evidencia": r.evidencia} for r in riesgos],
        "LONGITUD_TEXTO": len(texto or ""),
    }


@pipeline
def analizar_contrato(db: Session, tipo, texto, clausulas, hallazgos, riesgos,
                      client=None) -> AnalisisContratoIA:
    """Devuelve resumen y observaciones de IA, o un resultado vacío con el motivo del fallo."""
    client = client or OllamaClient()
    traza = {}
    started = perf_counter()
    tipo_texto = getattr(tipo, "value", str(tipo))
    try:
        with medir("retrieval_total"):
            fuentes = _fuentes_del_contrato(db, tipo_texto, riesgos, clausulas)
        documento = _documento_para_prompt(tipo_texto, texto, clausulas, hallazgos, riesgos)
        with medir("prompt_build"):
            messages, usadas = construir_prompt("", fuentes, documento=documento, tarea=TAREA_CONTRATO)
    except ValueError:
        return AnalisisContratoIA(disponible=False,
            motivo="El contrato excede el tamaño que esta función puede resumir.")
    except IAError as exc:
        return AnalisisContratoIA(disponible=False, motivo=str(exc))
    for intento in range(2):
        attempt_started = perf_counter()
        if intento:
            sumar("retry_count", 1)
        try:
            generado = client.generar(messages, AnalisisContratoModelo, intentos=1)
            with medir("citation_validation"):
                permitidas = validar_observaciones(generado, usadas, texto or "")
            traza.update({"llm_ms": round((perf_counter() - started) * 1000, 2),
                          "intentos_validacion": intento + 1,
                          "fuentes": [str(f.id) for f in usadas]})
            return AnalisisContratoIA(disponible=True, resumen=generado.resumen,
                observaciones=[ObservacionIA(observacion=o.observacion, evidencia=o.evidencia,
                    norma_id=permitidas[o.fuente].id if o.fuente else None)
                    for o in generado.observaciones],
                fuentes=usadas, trazabilidad=traza)
        except RespuestaInvalida as exc:
            rechazo(exc.motivo)
            traza["validacion_motivo"] = exc.motivo
            messages = [messages[0], messages[1], {"role": "user", "content":
                "Corrección del sistema: cada observación debe copiar un fragmento literal del "
                "contrato en 'evidencia' y no puede afirmar riesgos ni normas que no se te "
                "entregaron. Si no puedes cumplir, devuelve observaciones vacías."}]
        except IAError as exc:
            return AnalisisContratoIA(disponible=False, motivo=str(exc))
        finally:
            if intento:
                sumar("retry_ms", (perf_counter()-attempt_started)*1000)
    return AnalisisContratoIA(disponible=False,
        motivo="El servicio local de IA devolvió una respuesta que no pudo validarse.",
        trazabilidad=traza)
