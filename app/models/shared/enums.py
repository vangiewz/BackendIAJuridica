from enum import Enum

class AreaJuridica(str, Enum):
    """Las cuatro areas del documento de alcance, mas responsabilidad civil (HU-03)."""
    CONTRATOS = "contratos"
    OBLIGACIONES = "obligaciones"
    DERECHOS_REALES = "derechos_reales"
    SUCESIONES = "sucesiones"
    RESPONSABILIDAD_CIVIL = "responsabilidad_civil"

class TipoDocumento(str, Enum):
    """Documentos civiles contemplados en el alcance (HU-08)."""
    COMPRAVENTA = "compraventa"
    ARRENDAMIENTO = "arrendamiento"
    PRESTAMO = "prestamo"
    ACUERDO_CIVIL = "acuerdo_civil"
    OTRO = "otro"

class EstadoProceso(str, Enum):
    PENDIENTE = "pendiente"
    PROCESANDO = "procesando"
    COMPLETADO = "completado"
    FALLIDO = "fallido"

class SeveridadRiesgo(str, Enum):
    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"

class EstadoVigencia(str, Enum):
    """Vigencia verificada de una norma. La ingesta carga SIN_VERIFICAR y alguien la confirma."""
    VIGENTE = "vigente"
    DEROGADO = "derogado"
    MODIFICADO = "modificado"
    SIN_VERIFICAR = "sin_verificar"
