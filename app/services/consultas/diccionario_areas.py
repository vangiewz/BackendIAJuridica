from dataclasses import dataclass
from app.models.shared.enums import AreaJuridica

@dataclass(frozen=True)
class Termino:
    texto: str
    peso: float = 1.0

VERSION_DICCIONARIO = "1.0"

DICCIONARIO: dict[AreaJuridica, tuple[Termino, ...]] = {
    AreaJuridica.CONTRATOS: (
        # Capa 1
        Termino("mandato", 1.0), Termino("arrendamiento", 1.0), Termino("precio", 1.0),
        Termino("sociedad", 1.0), Termino("socio", 1.0), Termino("mandatario", 1.0),
        Termino("comprador", 1.0), Termino("rescate", 1.0), Termino("arrendatario", 1.0),
        Termino("mandante", 1.0), Termino("anulacion", 1.0),
        # Capa 2
        Termino("contrato", 1.0), Termino("compre", 1.0), Termino("compra", 1.0),
        Termino("venta", 1.0), Termino("vendedor", 1.0), Termino("terreno", 1.5),
        Termino("transferencia", 1.5), Termino("alquiler", 1.0), Termino("alquile", 1.0),
        Termino("alquilar", 1.0), Termino("inquilino", 1.0), Termino("prestamo", 1.0),
        Termino("firme", 1.0), Termino("firmamos", 1.0), Termino("cuotas", 1.0),
        Termino("anticipo", 1.0), Termino("minuta", 1.0), Termino("incumplio", 1.0),
        Termino("no cumplio", 1.0), Termino("plazo", 1.0),
    ),
    AreaJuridica.OBLIGACIONES: (
        # Capa 1
        Termino("prestacion", 1.0), Termino("recibo", 1.0), Termino("novacion", 1.0),
        Termino("moneda", 1.0), Termino("mancomunidad", 1.0), Termino("gestor", 1.0),
        Termino("garantia", 1.0),
        # Capa 2
        Termino("deuda", 1.0), Termino("debe", 1.0), Termino("me debe", 1.0),
        Termino("pagar", 1.0), Termino("pago", 1.0), Termino("no me paga", 1.0),
        Termino("cobrar", 1.0), Termino("plazo vencido", 1.0), Termino("intereses", 1.0),
        Termino("garante", 1.0), Termino("fiador", 1.0),
    ),
    AreaJuridica.DERECHOS_REALES: (
        # Capa 1
        Termino("obra", 1.0), Termino("agua", 1.0), Termino("muro", 1.0),
        Termino("superficie", 1.0), Termino("fundo", 1.0), Termino("medianeria", 1.0),
        Termino("acueducto", 1.0), Termino("servidumbre", 1.0), Termino("arbol", 1.0),
        Termino("distancia", 1.0), Termino("copropietario", 1.0), Termino("paso", 1.0),
        # Capa 2
        Termino("propiedad", 1.0), Termino("propietario", 1.0), Termino("dueno", 1.0),
        Termino("posesion", 1.0), Termino("terreno", 1.0), Termino("lote", 1.0),
        Termino("casa", 1.0), Termino("vecino", 1.0), Termino("linde", 1.0),
        Termino("cerco", 1.0), Termino("usucapion", 2.0), Termino("anticretico", 1.0),
        Termino("hipoteca", 1.0), Termino("invadio", 1.0), Termino("construyo", 1.0),
    ),
    AreaJuridica.SUCESIONES: (
        # Capa 1
        Termino("legado", 1.0), Termino("conyuge", 1.0), Termino("colacion", 1.0),
        Termino("ascendiente", 1.0), Termino("descendiente", 1.0), Termino("acrecimiento", 1.0),
        Termino("legatario", 1.0), Termino("desheredacion", 1.0), Termino("indignidad", 1.0),
        Termino("conviviente", 1.0),
        # Capa 2 (testamento se consolida aqui con peso 2.0)
        Termino("herencia", 2.0), Termino("heredero", 2.0), Termino("heredar", 1.0),
        Termino("fallecio", 1.0), Termino("murio", 1.0), Termino("difunto", 1.0),
        Termino("testamento", 2.0), Termino("legitima", 1.0), Termino("sucesion", 1.0),
        Termino("reparto de bienes", 1.0), Termino("papa fallecio", 1.0),
    ),
    AreaJuridica.RESPONSABILIDAD_CIVIL: (
        # Capa 1 y 2 consolidadas
        Termino("dano", 1.0), Termino("perjuicio", 1.0), Termino("culpa", 1.0),
        Termino("dolo", 1.0), Termino("resarcimiento", 1.0), Termino("ilicito", 1.0),
        Termino("indemnizacion", 1.5), Termino("responsabilidad", 1.0),
        Termino("dano moral", 1.0), Termino("choque", 1.0), Termino("chocaron", 1.0),
        Termino("accidente", 1.0), Termino("lesiones", 1.0), Termino("me perjudico", 1.0),
        Termino("negligencia", 1.0),
    ),
}
