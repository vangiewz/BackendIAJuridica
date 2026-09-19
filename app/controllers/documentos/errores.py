class DocumentoNoEncontradoError(Exception):
    pass

class TamanoExcedidoError(Exception):
    pass

class MismoDocumentoError(Exception):
    """Se pidio comparar un documento consigo mismo."""

class DocumentoSinTextoComparableError(Exception):
    """El documento no llego a tener texto extraido, asi que no hay nada que comparar."""
