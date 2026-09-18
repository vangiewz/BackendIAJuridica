from app.models.shared.enums import SeveridadRiesgo
from app.services.contratos.catalogo_riesgos import Riesgo, ContextoContrato, Regla

def _regla_sin_clausulas(ctx: ContextoContrato) -> Riesgo | None:
    if len(ctx.clausulas) == 0:
        return Riesgo(
            codigo='GEN-SIN-CLAUSULAS',
            titulo='No se detectaron cláusulas estructuradas',
            severidad=SeveridadRiesgo.MEDIA,
            articulos=(493,),
            explicacion='No se reconoció una estructura de cláusulas. El art. 493 establece que si las partes convinieron una forma determinada, esa forma es la exigible para la validez. Esto puede deberse a una limitación del sistema para identificar los encabezados en el formato proporcionado.',
            evidencia=None,
            inicio=None,
            clausula=None
        )
    return None

def _regla_sin_fecha(ctx: ContextoContrato) -> Riesgo | None:
    if not any(h.tipo == 'fecha' for h in ctx.hallazgos):
        return Riesgo(
            codigo='GEN-SIN-FECHA',
            titulo='Falta fecha del contrato',
            severidad=SeveridadRiesgo.MEDIA,
            articulos=(493,),
            explicacion='No se detectó una fecha en el documento. La fecha es fundamental para determinar el momento desde el cual nacen las obligaciones.',
            evidencia=None,
            inicio=None,
            clausula=None
        )
    return None

def _regla_sin_cedula(ctx: ContextoContrato) -> Riesgo | None:
    if not any(h.tipo == 'cedula' for h in ctx.hallazgos):
        return Riesgo(
            codigo='GEN-SIN-CEDULA',
            titulo='Falta documento de identidad de las partes',
            severidad=SeveridadRiesgo.ALTA,
            articulos=(549,),
            explicacion='No se encontró ningún número de cédula de identidad. El art. 549 establece que el contrato es nulo por faltar en el objeto los requisitos señalados por la ley; identificar a las partes es uno de ellos.',
            evidencia=None,
            inicio=None,
            clausula=None
        )
    return None

REGLAS_COMUNES: tuple[Regla, ...] = (
    _regla_sin_clausulas,
    _regla_sin_fecha,
    _regla_sin_cedula,
)
