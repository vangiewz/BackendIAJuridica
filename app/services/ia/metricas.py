"""Tiempos por ejecución. ContextVar evita mezclar usuarios; nunca recibe contenido."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import json
import logging
from time import perf_counter
from threading import RLock

_actual = ContextVar("metricas_ia", default=None)
logger = logging.getLogger(__name__)
ETAPAS = ("preparation", "classification", "expansion", "embedding", "lexical", "vector",
          "rrf", "retrieval_total", "prompt_build", "model_check", "llm_load", "llm_prompt",
          "llm_generation", "llm_http", "json_parse", "pydantic", "citation_validation",
          "context_validation", "persistence", "progress_persistence", "retry")


def sumar(clave, valor):
    metrics = _actual.get()
    if metrics is not None:
        with metrics["_lock"]:
            metrics[clave] = metrics.get(clave, 0) + valor


@contextmanager
def medir(etapa):
    tick = perf_counter()
    try:
        yield
    finally:
        sumar(etapa + "_ms", (perf_counter()-tick)*1000)


def rechazo(motivo):
    metrics = _actual.get()
    if metrics is not None:
        with metrics["_lock"]:
            metrics["rejection_reasons"].append(motivo)


def registrar_llm(datos, modelo):
    metrics = _actual.get()
    if metrics is None:
        return
    metrics["model"] = modelo
    sumar("qwen_calls", 1)
    for campo, etapa in (("load_duration", "llm_load"), ("prompt_eval_duration", "llm_prompt"),
                         ("eval_duration", "llm_generation")):
        if isinstance(datos.get(campo), (float, int)):
            sumar(etapa + "_ms", datos[campo]/1e6)
    for campo in ("prompt_eval_count", "eval_count"):
        if isinstance(datos.get(campo), int):
            sumar(campo, datos[campo])
    if all(isinstance(datos.get(k), (float, int)) for k in
           ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration")):
        sumar("llm_other_ms", max(0, datos["total_duration"] - datos["load_duration"] -
              datos["prompt_eval_duration"] - datos["eval_duration"])/1e6)


def instantanea():
    metrics = _actual.get()
    if metrics is None:
        return {}
    with metrics["_lock"]:
        return {k: round(v, 3) if isinstance(v, float) else list(v) if isinstance(v, list) else v
                for k, v in metrics.items() if k != "_lock"}


def pipeline(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        from app.core.config import get_settings
        root = _actual.get() is None
        token = None
        if root:
            token = _actual.set({**{e + "_ms": 0.0 for e in ETAPAS},
                "retry_count": 0, "qwen_calls": 0, "rejection_reasons": [], "_lock": RLock()})
        tick = perf_counter()
        result = None
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            metrics = instantanea()
            metrics["total_ms"] = round((perf_counter()-tick)*1000, 3)
            response = getattr(result, "respuesta", result)
            if hasattr(response, "trazabilidad"):
                metrics["sources"] = len(getattr(response, "fuentes", []))
                response.trazabilidad["metricas"] = metrics
            if root:
                _actual.reset(token)
                if get_settings().environment == "development":
                    logger.info("ia_pipeline %s", json.dumps(metrics, ensure_ascii=True))
    return wrapped
