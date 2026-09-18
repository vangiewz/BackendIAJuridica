import re
from app.models.shared.enums import SeveridadRiesgo
from app.services.contratos.catalogo_riesgos import Riesgo, ContextoContrato, Regla

def _regla_interes_pactado(ctx: ContextoContrato) -> Riesgo | None:
    match = re.search(r'(%|\binteres\w*)', ctx.texto_normalizado)
    if match:
        inicio = match.start()
        fin = match.end()
        evidencia = ctx.texto[inicio:fin]
        
        tasa_texto = "en el documento"
        m_tasa = re.search(r'(\d+(?:[\.,]\d+)?)\s*%', ctx.texto_normalizado)
        if m_tasa:
            tasa_texto = f"del {m_tasa.group(1)}%"
            inicio = m_tasa.start()
            fin = m_tasa.end()
            evidencia = ctx.texto[inicio:fin]

        clausula = next((c.orden for c in ctx.clausulas if c.inicio <= inicio < c.fin), None)
        
        return Riesgo(
            codigo='PR-INTERES-PACTADO',
            titulo='Se pactó el pago de intereses',
            severidad=SeveridadRiesgo.MEDIA,
            articulos=(413,),
            explicacion=f'Se pactó un interés {tasa_texto}. El art. 413 califica como usura el cobro de intereses en tasa superior a la máxima legalmente permitida. Ese máximo no lo fija el Código Civil sino la normativa financiera, que este sistema no tiene cargada: verificá la tasa vigente.',
            evidencia=evidencia,
            inicio=inicio,
            clausula=clausula
        )
    return None

def _regla_interes_capitalizado(ctx: ContextoContrato) -> Riesgo | None:
    texto = ctx.texto_normalizado
    match_int = re.search(r'\binteres\w*', texto)
    match_cap = re.search(r'\bcapitaliz\w*', texto)
    
    if match_int and match_cap:
        if abs(match_int.start() - match_cap.start()) <= 150:
            inicio = min(match_int.start(), match_cap.start())
            fin = max(match_int.end(), match_cap.end())
            evidencia = ctx.texto[inicio:fin]
            clausula = next((c.orden for c in ctx.clausulas if c.inicio <= inicio < c.fin), None)

            return Riesgo(
                codigo='PR-INTERES-CAPITALIZADO',
                titulo='Posible capitalización de intereses',
                severidad=SeveridadRiesgo.ALTA,
                articulos=(413,),
                explicacion='El art. 413 incluye expresamente los intereses capitalizados entre los que constituyen usura y quedan sujetos a restitución.',
                evidencia=evidencia,
                inicio=inicio,
                clausula=clausula
            )
    return None

def _regla_sin_plazo_devolucion(ctx: ContextoContrato) -> Riesgo | None:
    if not any(h.tipo == 'plazo' for h in ctx.hallazgos):
        return Riesgo(
            codigo='PR-SIN-PLAZO-DEVOLUCION',
            titulo='No se estipuló plazo de devolución',
            severidad=SeveridadRiesgo.MEDIA,
            articulos=(493,),
            explicacion='No se detectó un plazo. Es importante estipular el tiempo para la devolución del préstamo.',
            evidencia=None,
            inicio=None,
            clausula=None
        )
    return None

REGLAS_PRESTAMO: tuple[Regla, ...] = (
    _regla_interes_pactado,
    _regla_interes_capitalizado,
    _regla_sin_plazo_devolucion,
)
