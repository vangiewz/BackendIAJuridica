"""Transporte local Ollama. Sin reglas jurídicas ni logs del contenido privado."""
import logging
import atexit
import json
import math
import time
from functools import lru_cache
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.services.ia.metricas import medir, registrar_llm, rechazo, sumar

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


@lru_cache(maxsize=4)
def _http_local(url):
    # httpx.Client admite uso entre hilos. Solo se cachea transporte, nunca mensajes.
    # La URL ya pasó la validación de loopback; no proxies ni redirecciones.
    client = httpx.Client(base_url=url, trust_env=False, follow_redirects=False)
    atexit.register(client.close)
    return client


class IAError(Exception):
    """Error público seguro: nunca incluye cuerpo HTTP, consulta ni documento."""


class IANoDisponible(IAError):
    def __init__(self):
        super().__init__("El servicio local de inteligencia artificial no está disponible.")


class RespuestaInvalida(IAError):
    """El motivo es interno: sirve para trazas y reintentos, nunca se muestra al usuario."""

    def __init__(self, motivo: str = "no_especificado", detalle: str = ""):
        self.motivo = motivo
        # Qué disparó el rechazo (el número o el identificador concreto). No se le muestra
        # al usuario; sirve para que una traza diga por qué se descartó una respuesta.
        self.detalle = detalle
        super().__init__("El servicio local de IA devolvió una respuesta que no pudo validarse.")


class OllamaClient:
    def __init__(self, settings: Settings | None = None, transport=None):
        self.settings = settings or get_settings()
        self.transport = transport
        self.last_metrics = {}

    def _request(self, method: str, path: str, payload=None, timeout=None) -> dict:
        started = time.perf_counter()
        status = "error"
        data = {}
        try:
            # No proxies de entorno ni redirecciones hacia destinos externos.
            from contextlib import nullcontext
            connection = (httpx.Client(base_url=self.settings.ollama_url, trust_env=False,
                          follow_redirects=False, transport=self.transport)
                          if self.transport is not None else nullcontext(_http_local(self.settings.ollama_url)))
            with connection as client:
                response = client.request(method, path, json=payload,
                    timeout=httpx.Timeout(timeout or self.settings.ollama_timeout, connect=3))
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict) or "error" in data:
                    raise RespuestaInvalida()
                status = "ok"
                self.last_metrics = {key: data[key] for key in (
                    "prompt_eval_count", "eval_count", "total_duration", "load_duration",
                    "prompt_eval_duration", "eval_duration")
                    if type(data.get(key)) in (int, float)}
                if path == "/api/chat":
                    registrar_llm(data, (payload or {}).get("model", ""))
                return data
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError):
            raise IANoDisponible() from None
        except (ValueError, httpx.ProtocolError):
            raise RespuestaInvalida() from None
        finally:
            if self.settings.environment == "development":
                logger.info("ia_http modelo=%s duracion_ms=%.1f estado=%s tokens_entrada=%s tokens_salida=%s",
                            (payload or {}).get("model", ""),
                            (time.perf_counter() - started) * 1000, status,
                            data.get("prompt_eval_count") if isinstance(data, dict) else None,
                            data.get("eval_count") if isinstance(data, dict) else None)

    def modelos(self) -> dict[str, str]:
        data = self._request("GET", "/api/tags", timeout=5)
        try:
            return {item["name"]: item["digest"] for item in data["models"]}
        except (KeyError, TypeError):
            raise RespuestaInvalida() from None

    def comprobar_modelo(self, model: str, capability: str) -> None:
        data = self._request("POST", "/api/show", {"model": model}, timeout=5)
        if data.get("remote_host") or data.get("remote_model"):
            raise IANoDisponible()
        if capability not in data.get("capabilities", []):
            raise RespuestaInvalida()

    def generar(self, messages: list[dict], schema: type[T], intentos: int = 2,
                timeout: float | None = None) -> T:
        with medir("model_check"):
            self.comprobar_modelo(self.settings.ollama_model, "completion")
        limit = self.settings.ollama_num_predict
        complejo = schema.__name__ == "RespuestaCasoComplejo"
        if complejo:
            # Un análisis de ocho cuestiones con resumen y conclusión no entra en 2200
            # tokens: se truncaba y salía una respuesta a medias. La calidad manda sobre
            # el tiempo, así que el presupuesto es el que la respuesta necesite.
            # Dimensionado por el contenido, no por el reloj. Ocho apartados de un párrafo
            # desarrollado, más resumen y conclusión, rondan las 3500 fichas; con 3500 de
            # tope una respuesta completa se cortaba al final y se descartaba entera
            # ("salida_truncada"). Es un techo: si el modelo termina antes, no cuesta más.
            limit = 6000
        elif schema.__name__ == "DescomposicionModelo":
            limit = min(limit, self.settings.ollama_short_num_predict)
        elif schema.__name__ == "RevisionModelo":
            limit = min(limit, 400)
        elif schema.__name__ in ("RespuestaModelo", "RespuestaConContexto", "RespuestaSeleccion"):
            # El tope de RAG existía para bajar segundos; una consulta con varios
            # fundamentos necesita más espacio que eso.
            limit = max(self.settings.ollama_rag_num_predict, 2400)
        elif schema.__name__ == "RespuestaSimpleModelo":
            # Una respuesta desarrollada de 350-600 palabras ronda las 1200 fichas. Con
            # el tope general de 1800 sobra margen y, junto al presupuesto de datos del
            # prompt, todo entra en num_ctx sin que la salida se corte a mitad.
            limit = max(self.settings.ollama_num_predict, 1800)
        elif schema.__name__ == "RespuestaAyudaModelo":
            limit = min(limit, self.settings.ollama_short_num_predict, 300)
        elif schema.__name__ == "RespuestaDocumentoModelo":
            limit = min(limit, self.settings.ollama_short_num_predict, 320)
        elif schema.__name__ in ("ExplicacionModelo", "AnalisisContratoModelo", "ContextoIA"):
            limit = min(limit, self.settings.ollama_short_num_predict)
        payload = {
            "model": self.settings.ollama_model, "messages": messages,
            "stream": False, "think": False, "format": schema.model_json_schema(),
            "keep_alive": self.settings.ollama_keep_alive,
            "options": {"temperature": self.settings.ollama_temperature,
                        # El caso complejo lleva hasta 20 fuentes fragmentadas: necesita
                        # ventana para el prompt y para una salida larga.
                        "num_ctx": max(16384, self.settings.ollama_num_ctx) if complejo else self.settings.ollama_num_ctx,
                        "num_predict": limit},
        }
        reason = "no_especificado"
        salida_original = None
        for attempt in range(min(max(intentos, 1), 2)):
            if attempt:
                sumar("retry_count", 1)
            with medir("llm_http"):
                # Un caso complejo genera durante minutos: con el timeout normal la
                # petición se cortaba a los 180 s y la respuesta buena se perdía entera.
                data = self._request("POST", "/api/chat", payload,
                                     timeout=timeout or (600 if complejo else None))
            mensaje = data.get("message")
            salida_original = mensaje.get("content") if isinstance(mensaje, dict) else None
            try:
                if data.get("done") is not True or data.get("done_reason") == "length":
                    raise RespuestaInvalida("salida_truncada")
                with medir("json_parse"):
                    parsed = json.loads(data["message"]["content"])
                salida_original = parsed
                with medir("pydantic"):
                    return schema.model_validate(parsed)
            except (KeyError, TypeError, ValueError, RespuestaInvalida) as exc:
                reason = (exc.motivo if isinstance(exc, RespuestaInvalida) else
                          "schema_invalido" if isinstance(exc, ValidationError) else "json_invalido")
                rechazo(reason)
                # Un solo reintento, sin reenviar salida inválida como instrucciones.
                continue
        exc = RespuestaInvalida(reason)
        # Solo el orquestador con depuración local opt-in conserva este dato. El mensaje
        # público de la excepción sigue sin incluir la salida privada del modelo.
        exc.salida_estructurada_original = salida_original
        raise exc

    def embeddings(self, texts: list[str]) -> list[list[float]]:
        if not texts or any(not text.strip() for text in texts):
            raise ValueError("Se requieren textos no vacíos para generar embeddings")
        self.comprobar_modelo(self.settings.embedding_model, "embedding")
        data = self._request("POST", "/api/embed", {
            "model": self.settings.embedding_model, "input": texts,
            "truncate": False, "keep_alive": self.settings.embedding_keep_alive,
            "options": {"num_gpu": self.settings.embedding_num_gpu},
        })
        vectors = data.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise RespuestaInvalida()
        dimensions = None
        for vector in vectors:
            if (not isinstance(vector, list) or not vector
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector)
                    or not any(vector)):
                raise RespuestaInvalida()
            dimensions = dimensions or len(vector)
            if len(vector) != dimensions:
                raise RespuestaInvalida()
        return vectors
