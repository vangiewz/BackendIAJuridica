"""HU-13: explicación en lenguaje sencillo de un artículo concreto.

El modelo recibe solo ese artículo y su ubicación jerárquica. El texto original se
devuelve tal cual desde la base: la explicación lo acompaña, nunca lo reemplaza.
"""
from time import perf_counter

from app.models.conocimiento.norma import Norma
from app.models.ia.esquemas import ExplicacionArticuloIA, ExplicacionModelo
from app.services.ia.fuentes import fuente_de_norma
from app.services.ia.ollama_client import IAError, OllamaClient, RespuestaInvalida
from app.services.ia.prompts import CORRECCIONES, TAREA_EXPLICACION, construir_prompt, VERSION_PROMPT
from app.services.ia.validacion import verificar_prosa
from app.services.ia.cache_publica import explicaciones
from app.services.ia.metricas import pipeline, medir, sumar, rechazo


@pipeline
def explicar_articulo(norma: Norma, client=None) -> ExplicacionArticuloIA:
    client = client or OllamaClient()
    fuente = fuente_de_norma(norma)
    settings = client.settings
    cache_key = None
    if settings.ia_explanation_cache_size and settings.ia_explanation_cache_ttl:
        try:
            client.comprobar_modelo(settings.ollama_model, "completion")
            digest = client.modelos().get(settings.ollama_model)
            if digest:
                cache_key = (settings.ollama_url, settings.ollama_model, digest,
                    fuente.contenido_hash, fuente.version, VERSION_PROMPT,
                    settings.ollama_temperature, settings.ollama_num_ctx,
                    settings.ollama_num_predict, settings.ollama_short_num_predict)
                cached = explicaciones.obtener(cache_key, settings.ia_explanation_cache_ttl,
                                               settings.ia_explanation_cache_size)
                if cached:
                    cached.trazabilidad = {"cache_hit": True, "prompt_version": VERSION_PROMPT}
                    return cached
        except IAError as exc:
            return ExplicacionArticuloIA(disponible=False, articulo=norma.articulo,
                texto_original=norma.texto, motivo=str(exc))
    ubicacion = {campo: getattr(norma, campo) for campo in
                 ("libro", "parte", "titulo", "capitulo", "seccion") if getattr(norma, campo)}
    started = perf_counter()
    try:
        with medir("prompt_build"):
            messages, usadas = construir_prompt("", [fuente], documento={"UBICACION": ubicacion},
                                                tarea=TAREA_EXPLICACION)
    except ValueError:
        return ExplicacionArticuloIA(disponible=False, articulo=norma.articulo,
            texto_original=norma.texto, motivo="El artículo excede el tamaño admitido.")
    if not usadas:
        return ExplicacionArticuloIA(disponible=False, articulo=norma.articulo,
            texto_original=norma.texto, motivo="El artículo excede el tamaño admitido.")
    traza = {}
    for intento in range(2):
        attempt_started = perf_counter()
        if intento:
            sumar("retry_count", 1)
        try:
            generado = client.generar(messages, ExplicacionModelo, intentos=1)
            # El artículo explicado es su propia fuente: nada puede venir de otra norma.
            with medir("citation_validation"):
                verificar_prosa(generado.explicacion, usadas)
                if generado.ejemplo:
                    verificar_prosa(generado.ejemplo, usadas)
            traza.update({"llm_ms": round((perf_counter() - started) * 1000, 2),
                          "intentos_validacion": intento + 1})
            resultado = ExplicacionArticuloIA(disponible=True, articulo=norma.articulo,
                texto_original=norma.texto, explicacion=generado.explicacion,
                ejemplo=generado.ejemplo or None, fuente=fuente, trazabilidad=traza)
            if cache_key:
                explicaciones.guardar(cache_key, resultado, settings.ia_explanation_cache_size)
            return resultado
        except RespuestaInvalida as exc:
            rechazo(exc.motivo)
            traza["validacion_motivo"] = exc.motivo
            messages = [messages[0], messages[1], {"role": "user", "content":
                "Corrección del sistema: " + CORRECCIONES.get(exc.motivo, CORRECCIONES["no_especificado"]) +
                " Explica solo lo que dice el artículo entregado; el ejemplo va sin cantidades ni fechas."}]
        except IAError as exc:
            return ExplicacionArticuloIA(disponible=False, articulo=norma.articulo,
                texto_original=norma.texto, motivo=str(exc))
        finally:
            if intento:
                sumar("retry_ms", (perf_counter()-attempt_started)*1000)
    return ExplicacionArticuloIA(disponible=False, articulo=norma.articulo,
        texto_original=norma.texto, trazabilidad=traza,
        motivo="El servicio local de IA devolvió una respuesta que no pudo validarse.")
