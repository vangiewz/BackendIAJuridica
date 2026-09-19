class CorpusIncompletoError(Exception):
    """El parseo no alcanzo el total esperado de la fuente. No se escribe nada."""

class FuenteNoEncontradaError(Exception):
    """El archivo de la fuente no existe en data/normativa/."""

class FuenteNoSoportadaError(Exception):
    """La clave de fuente pedida no esta en el registro de perfiles."""

class FuenteNoProcesableError(Exception):
    """El archivo no se pudo leer como PDF o no tiene capa de texto."""
