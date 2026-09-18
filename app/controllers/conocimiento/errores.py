class CorpusIncompletoError(Exception):
    """El parseo no alcanzo el total esperado de la fuente. No se escribe nada."""

class FuenteNoEncontradaError(Exception):
    """El archivo de la fuente no existe en data/normativa/."""
