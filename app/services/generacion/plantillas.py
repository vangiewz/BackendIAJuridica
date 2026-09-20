"""HU-14: estructura fija de los borradores dentro del alcance.

El sistema no genera "cualquier contrato": cada tipo admitido declara qué datos necesita
y qué cláusulas tiene. El modelo redacta el texto de esas cláusulas; ni el esqueleto ni
los datos de las partes dependen de él.
"""
import re
from dataclasses import dataclass, field

from app.models.shared.enums import TipoDocumento


@dataclass(frozen=True)
class Campo:
    clave: str
    etiqueta: str
    obligatorio: bool = True


@dataclass(frozen=True)
class Plantilla:
    tipo: TipoDocumento
    titulo: str
    campos: tuple[Campo, ...]
    clausulas: tuple[str, ...]
    # Términos de búsqueda de normativa: no contienen números de artículo ni conclusiones.
    consulta_normativa: str = ""
    notas: tuple[str, ...] = field(default_factory=tuple)

    @property
    def obligatorios(self):
        return tuple(c for c in self.campos if c.obligatorio)


PARTES_COMUNES = (
    Campo("vendedor_nombre", "Nombre completo de la parte que transfiere o entrega"),
    Campo("vendedor_ci", "Documento de identidad de esa parte"),
    Campo("comprador_nombre", "Nombre completo de la parte que recibe"),
    Campo("comprador_ci", "Documento de identidad de esa parte"),
    Campo("lugar", "Lugar de suscripción"),
    Campo("fecha", "Fecha de suscripción"),
)

PLANTILLAS = {
    TipoDocumento.COMPRAVENTA: Plantilla(
        tipo=TipoDocumento.COMPRAVENTA,
        titulo="CONTRATO DE COMPRAVENTA",
        campos=PARTES_COMUNES + (
            Campo("objeto", "Descripción del bien que se vende"),
            Campo("precio", "Precio convenido y moneda"),
            Campo("forma_pago", "Forma y plazo de pago"),
            Campo("entrega", "Momento y lugar de entrega", obligatorio=False),
        ),
        clausulas=("OBJETO", "PRECIO", "FORMA DE PAGO", "ENTREGA",
                   "OBLIGACIONES DE LAS PARTES", "CONFORMIDAD"),
        consulta_normativa="compraventa obligaciones del vendedor entrega precio evicción",
    ),
    TipoDocumento.ARRENDAMIENTO: Plantilla(
        tipo=TipoDocumento.ARRENDAMIENTO,
        titulo="CONTRATO DE ARRENDAMIENTO",
        campos=(
            Campo("arrendador_nombre", "Nombre completo del arrendador"),
            Campo("arrendador_ci", "Documento de identidad del arrendador"),
            Campo("arrendatario_nombre", "Nombre completo del arrendatario"),
            Campo("arrendatario_ci", "Documento de identidad del arrendatario"),
            Campo("lugar", "Lugar de suscripción"),
            Campo("fecha", "Fecha de suscripción"),
            Campo("inmueble", "Descripción y dirección del inmueble"),
            Campo("canon", "Canon de arrendamiento y moneda"),
            Campo("plazo", "Plazo del contrato"),
            Campo("dia_pago", "Día de pago del canon", obligatorio=False),
            Campo("destino", "Destino o uso del inmueble", obligatorio=False),
        ),
        clausulas=("OBJETO", "CANON Y FORMA DE PAGO", "PLAZO", "DESTINO DEL INMUEBLE",
                   "OBLIGACIONES DE LAS PARTES", "CONFORMIDAD"),
        consulta_normativa="arrendamiento canon plazo obligaciones arrendador arrendatario",
    ),
    TipoDocumento.PRESTAMO: Plantilla(
        tipo=TipoDocumento.PRESTAMO,
        titulo="CONTRATO DE PRÉSTAMO",
        campos=(
            Campo("prestamista_nombre", "Nombre completo de quien presta"),
            Campo("prestamista_ci", "Documento de identidad de quien presta"),
            Campo("prestatario_nombre", "Nombre completo de quien recibe el préstamo"),
            Campo("prestatario_ci", "Documento de identidad de quien recibe"),
            Campo("lugar", "Lugar de suscripción"),
            Campo("fecha", "Fecha de suscripción"),
            Campo("monto", "Monto prestado y moneda"),
            Campo("plazo_devolucion", "Plazo o fecha de devolución"),
            Campo("interes", "Interés convenido, si lo hay", obligatorio=False),
            Campo("garantia", "Garantía ofrecida, si la hay", obligatorio=False),
        ),
        clausulas=("OBJETO Y MONTO", "PLAZO DE DEVOLUCIÓN", "INTERESES",
                   "OBLIGACIONES DE LAS PARTES", "CONFORMIDAD"),
        consulta_normativa="préstamo mutuo restitución intereses plazo obligaciones del mutuario",
    ),
}

TIPOS_SOPORTADOS = tuple(PLANTILLAS)


def obtener(tipo: TipoDocumento) -> Plantilla:
    if tipo not in PLANTILLAS:
        raise ValueError("Tipo de documento fuera del alcance de generación")
    return PLANTILLAS[tipo]


def faltantes(plantilla: Plantilla, datos: dict) -> list[str]:
    return [c.etiqueta for c in plantilla.obligatorios if not str(datos.get(c.clave, "")).strip()]


def marcador(etiqueta: str) -> str:
    """Un dato ausente se señala; nunca se rellena con un valor plausible."""
    return f"[FALTA: {etiqueta}]"


def datos_desde_contenido(plantilla: Plantilla, contenido: str) -> dict:
    """Recupera los datos de una versión ya guardada leyendo su bloque de partes.

    Evita duplicar la información en otra columna: el documento es su propia fuente.
    """
    por_etiqueta = {c.etiqueta: c.clave for c in plantilla.campos}
    datos = {}
    for linea in (contenido or "").splitlines():
        etiqueta, separador, valor = linea.partition(": ")
        clave = por_etiqueta.get(etiqueta.strip())
        if separador and clave and not valor.strip().startswith("[FALTA:"):
            datos[clave] = valor.strip()
    return datos


def faltantes_en_contenido(contenido: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\[FALTA:\s*(.+?)\]", contenido or "")))
