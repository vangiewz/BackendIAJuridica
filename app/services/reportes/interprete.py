"""Qwen traduce la petición a una especificación; nada más.

El modelo no ve datos de la base ni decide qué se ejecuta: devuelve una estructura que
después el catálogo acepta o rechaza. Si la rechaza, se le dice el motivo y se le da un
único reintento, igual que en el resto del proyecto.
"""
from typing import Callable

from app.models.reportes.esquemas import EspecificacionReporte
from app.services.ia.ollama_client import IAError, OllamaClient, RespuestaInvalida
from app.services.reportes.fidelidad import ajustar_a_lo_pedido
from app.services.reportes.prompt import construir_mensajes

INTENTOS = 2


class ReporteNoDisponibleError(Exception):
    """La IA local no pudo interpretar la petición."""


def interpretar(peticion: str, actual: EspecificacionReporte | None = None,
                validar: Callable[[EspecificacionReporte], None] | None = None,
                client: OllamaClient | None = None) -> EspecificacionReporte:
    client = client or OllamaClient()
    correccion: str | None = None
    ultimo_motivo = ""

    for intento in range(INTENTOS):
        mensajes = construir_mensajes(peticion, actual, correccion)
        try:
            spec = client.generar(mensajes, EspecificacionReporte, intentos=1)
        except RespuestaInvalida:
            # Formato ilegible: se reintenta sin corrección porque no hay motivo que dar.
            correccion, ultimo_motivo = None, "formato"
            continue
        except IAError as exc:
            raise ReporteNoDisponibleError(str(exc)) from None

        if not spec.entidad:
            # El modelo dice que no se puede: es una respuesta válida, no un fallo.
            return spec
        # Se recorta contra el texto real antes de validar: lo que el usuario no pidió
        # no llega ni a comprobarse contra el catálogo.
        spec = ajustar_a_lo_pedido(spec, peticion, actual)
        if validar is None:
            return spec
        try:
            validar(spec)
            return spec
        except Exception as exc:  # ReporteInvalido: el motivo es seguro de mostrar
            correccion, ultimo_motivo = str(exc), str(exc)
            if intento == INTENTOS - 1:
                # Se agotó el reintento: se devuelve como aclaración en vez de un error
                # opaco, para que el usuario sepa qué reformular.
                return EspecificacionReporte(aclaracion=ultimo_motivo)

    raise ReporteNoDisponibleError(
        "El servicio local de IA no pudo interpretar la solicitud. Probá reformularla.")
