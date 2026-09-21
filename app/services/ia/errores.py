"""Excepciones publicas y privadas para el manejo de la IA."""

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
