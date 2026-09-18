import re
from app.models.shared.enums import SeveridadRiesgo
from app.services.contratos.catalogo_riesgos import Riesgo, ContextoContrato, Regla

def _regla_precio_ausente(ctx: ContextoContrato) -> Riesgo | None:
    if not any(h.tipo in ('monto_bs', 'monto_usd') for h in ctx.hallazgos):
        return Riesgo(
            codigo='CV-PRECIO-AUSENTE',
            titulo='No se estipuló un precio de venta',
            severidad=SeveridadRiesgo.ALTA,
            articulos=(613,),
            explicacion='No se detectó un precio en el documento. El art. 613 solo presume el precio usual cuando se trata de cosas que el vendedor vende habitualmente; para una venta aislada, el precio no se presume.',
            evidencia=None,
            inicio=None,
            clausula=None
        )
    return None

def _regla_cosa_ajena(ctx: ContextoContrato) -> Riesgo | None:
    match = re.search(r'\b(cosa ajena|no es propietario)\b', ctx.texto_normalizado)
    if match:
        inicio = match.start()
        fin = match.end()
        evidencia = ctx.texto[inicio:fin]
        clausula = next((c.orden for c in ctx.clausulas if c.inicio <= inicio < c.fin), None)
        return Riesgo(
            codigo='CV-COSA-AJENA',
            titulo='Venta de cosa ajena',
            severidad=SeveridadRiesgo.ALTA,
            articulos=(595, 596),
            explicacion='El art. 595 no anula la venta de cosa ajena: obliga al vendedor a procurar la adquisición en favor del comprador, y el comprador se hace propietario recién cuando el vendedor adquiere la cosa.',
            evidencia=evidencia,
            inicio=inicio,
            clausula=clausula
        )
    return None

def _regla_venta_herencia(ctx: ContextoContrato) -> Riesgo | None:
    match = re.search(r'\b(venta de herencia|derechos hereditarios)\b', ctx.texto_normalizado)
    if match:
        inicio = match.start()
        fin = match.end()
        evidencia = ctx.texto[inicio:fin]
        clausula = next((c.orden for c in ctx.clausulas if c.inicio <= inicio < c.fin), None)
        return Riesgo(
            codigo='CV-VENTA-HERENCIA',
            titulo='Venta de derechos hereditarios',
            severidad=SeveridadRiesgo.MEDIA,
            articulos=(607,),
            explicacion='Se identificó una posible venta de derechos hereditarios. El art. 607 establece reglas específicas para este tipo de transferencia.',
            evidencia=evidencia,
            inicio=inicio,
            clausula=clausula
        )
    return None

REGLAS_COMPRAVENTA: tuple[Regla, ...] = (
    _regla_precio_ausente,
    _regla_cosa_ajena,
    _regla_venta_herencia,
)
