from dataclasses import dataclass
from app.models.shared.enums import TipoDocumento

@dataclass(frozen=True)
class Termino:
    texto: str        # ya normalizado, sin acentos
    peso: float = 1.0 # 1.0 por defecto; 2.0 si es inequivoco del tipo

DICCIONARIO: dict[TipoDocumento, tuple[Termino, ...]] = {
    TipoDocumento.COMPRAVENTA: (
        Termino("compraventa", 2.0),
        Termino("vendedor", 2.0),
        Termino("comprador", 2.0),
        Termino("precio de venta"),
        Termino("transferencia"),
        Termino("tradicion"),
        Termino("minuta de transferencia"),
        Termino("bien inmueble"),
        Termino("precio convenido"),
        Termino("saneamiento de ley"),
        Termino("folio real"),
        Termino("matricula"),
    ),
    TipoDocumento.ARRENDAMIENTO: (
        Termino("arrendamiento", 2.0),
        Termino("arrendador", 2.0),
        Termino("arrendatario", 2.0),
        Termino("canon", 1.5),
        Termino("alquiler"),
        Termino("mensualidad"),
        Termino("inmueble arrendado"),
        Termino("plazo del contrato"),
        Termino("deposito en garantia"),
        Termino("entrega del inmueble"),
    ),
    TipoDocumento.PRESTAMO: (
        Termino("prestamo", 2.0),
        Termino("mutuo", 2.0),
        Termino("prestamista", 2.0),
        Termino("prestatario", 2.0),
        Termino("deudor"),
        Termino("acreedor"),
        Termino("interes"),
        Termino("tasa de interes"),
        Termino("amortizacion"),
        Termino("capital prestado"),
        Termino("pagare"),
        Termino("plazo de devolucion"),
    ),
    TipoDocumento.ACUERDO_CIVIL: (
        Termino("transaccion", 2.0),
        Termino("conciliacion", 2.0),
        Termino("acuerdo transaccional", 2.0),
        Termino("las partes acuerdan"),
        Termino("de comun acuerdo"),
        Termino("desistimiento"),
        Termino("finiquito"),
        Termino("controversia"),
    ),
}

VERSION_DICCIONARIO_TIPOS = "1.0"
