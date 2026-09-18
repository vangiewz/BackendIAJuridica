import re
from app.models.shared.enums import SeveridadRiesgo
from app.services.contratos.catalogo_riesgos import Riesgo, ContextoContrato, Regla

def _regla_sin_plazo(ctx: ContextoContrato) -> Riesgo | None:
    if not any(h.tipo == 'plazo' for h in ctx.hallazgos):
        return Riesgo(
            codigo='AR-SIN-PLAZO',
            titulo='No se estipuló un plazo de arrendamiento',
            severidad=SeveridadRiesgo.MEDIA,
            articulos=(687,),
            explicacion='No se detectó un plazo. El art. 687 suple el silencio: un año para locales profesionales, industriales o comerciales, y para muebles el lapso al que se ajusta el canon.',
            evidencia=None,
            inicio=None,
            clausula=None
        )
    return None

def _regla_subarriendo_sin_autorizacion(ctx: ContextoContrato) -> Riesgo | None:
    texto = ctx.texto_normalizado
    match_subarr = re.search(r'\bsubarr\w*', texto)
    if not match_subarr:
        return None

    inicio = match_subarr.start()
    fin = match_subarr.end()

    # Si hay prohibicion cerca (ventana de 60 caracteres), no es riesgo
    ventana_inicio = max(0, inicio - 60)
    ventana_fin = min(len(texto), fin + 60)
    if re.search(r'\bprohib\w*', texto[ventana_inicio:ventana_fin]):
        return None

    # Si hay autorizacion expresa en algun lado, tampoco
    if re.search(r'\b(autorizacion expresa|autoriza expresamente)\b', texto):
        return None

    evidencia = ctx.texto[inicio:fin]
    clausula = next((c.orden for c in ctx.clausulas if c.inicio <= inicio < c.fin), None)
    
    return Riesgo(
        codigo='AR-SUBARRIENDO-SIN-AUTORIZACION',
        titulo='Subarriendo sin autorización expresa',
        severidad=SeveridadRiesgo.ALTA,
        articulos=(707,),
        explicacion='Se menciona la posibilidad de subarriendo pero no consta una autorización expresa explícita. El art. 707 exige el consentimiento del arrendador para subarrendar.',
        evidencia=evidencia,
        inicio=inicio,
        clausula=clausula
    )

def _regla_anticretico_simultaneo(ctx: ContextoContrato) -> Riesgo | None:
    texto = ctx.texto_normalizado
    match_arr = re.search(r'\barrendamient\w*|\barriend\w*|\balquile\w*|\balquila\w*', texto)
    match_ant = re.search(r'\banticresi\w*|\banticretic\w*', texto)
    
    if match_arr and match_ant:
        inicio = match_ant.start()
        fin = match_ant.end()
        evidencia = ctx.texto[inicio:fin]
        clausula = next((c.orden for c in ctx.clausulas if c.inicio <= inicio < c.fin), None)

        return Riesgo(
            codigo='AR-ANTICRETICO-SIMULTANEO',
            titulo='Posible arrendamiento y anticresis simultáneos',
            severidad=SeveridadRiesgo.ALTA,
            articulos=(716,),
            explicacion='El art. 716 prohíbe dar al mismo tiempo en arriendo y en anticresis un fundo urbano destinado a vivienda, y sanciona la contravención con la nulidad de la anticresis. Este sistema no puede verificar automáticamente si se trata de un fundo urbano destinado a vivienda.',
            evidencia=evidencia,
            inicio=inicio,
            clausula=clausula
        )
    return None

REGLAS_ARRENDAMIENTO: tuple[Regla, ...] = (
    _regla_sin_plazo,
    _regla_subarriendo_sin_autorizacion,
    _regla_anticretico_simultaneo,
)
