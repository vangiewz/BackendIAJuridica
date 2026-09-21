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
    # Cómo se escribe este dato. La pantalla lo muestra en gris dentro del campo vacío: sirve de guía y NO
    # se usa como valor. Se escribe con el formato que el sistema entiende mejor (nombre completo, fecha
    # con día, mes y año, moneda con su nombre), porque el usuario copia el estilo del ejemplo.
    ejemplo: str = ""


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
    Campo("vendedor_nombre", "Nombre completo de la parte que transfiere o entrega", ejemplo="Ej.: Ana María Rojas Vaca"),
    Campo("vendedor_ci", "Documento de identidad de esa parte", ejemplo="Ej.: 4587963"),
    Campo("comprador_nombre", "Nombre completo de la parte que recibe", ejemplo="Ej.: Carlos Eduardo Molina Peña"),
    Campo("comprador_ci", "Documento de identidad de esa parte", ejemplo="Ej.: 6123480"),
    Campo("lugar", "Lugar de suscripción", ejemplo="Ej.: Santa Cruz de la Sierra (sin siglas)"),
    Campo("fecha", "Fecha de suscripción", ejemplo="Ej.: 1 de octubre de 2026 (con día, mes y año)"),
)

PLANTILLAS = {
    TipoDocumento.COMPRAVENTA: Plantilla(
        tipo=TipoDocumento.COMPRAVENTA,
        titulo="CONTRATO DE COMPRAVENTA",
        campos=PARTES_COMUNES + (
            Campo("objeto", "Descripción del bien que se vende", ejemplo="Ej.: Un vehículo Toyota Hilux, año 2018, placa 1234-ABC"),
            Campo("precio", "Precio convenido y moneda", ejemplo="Ej.: 25.000 bolivianos"),
            Campo("forma_pago", "Forma y plazo de pago", ejemplo="Ej.: Al contado, con transferencia bancaria, el día de la firma"),
            Campo("entrega", "Momento y lugar de entrega", obligatorio=False, ejemplo="Ej.: El 15 de octubre de 2026, en el domicilio del comprador"),
        ),
        clausulas=("OBJETO", "PRECIO", "FORMA DE PAGO", "ENTREGA",
                   "OBLIGACIONES DE LAS PARTES", "CONFORMIDAD"),
        consulta_normativa="compraventa obligaciones del vendedor entrega precio evicción",
    ),
    TipoDocumento.ARRENDAMIENTO: Plantilla(
        tipo=TipoDocumento.ARRENDAMIENTO,
        titulo="CONTRATO DE ARRENDAMIENTO",
        campos=(
            Campo("arrendador_nombre", "Nombre completo del arrendador", ejemplo="Ej.: Ana María Rojas Vaca"),
            Campo("arrendador_ci", "Documento de identidad del arrendador", ejemplo="Ej.: 4587963"),
            Campo("arrendatario_nombre", "Nombre completo del arrendatario", ejemplo="Ej.: Carlos Eduardo Molina Peña"),
            Campo("arrendatario_ci", "Documento de identidad del arrendatario", ejemplo="Ej.: 6123480"),
            Campo("lugar", "Lugar de suscripción", ejemplo="Ej.: Santa Cruz de la Sierra (sin siglas)"),
            Campo("fecha", "Fecha de suscripción", ejemplo="Ej.: 1 de octubre de 2026 (con día, mes y año)"),
            Campo("inmueble", "Descripción y dirección del inmueble", ejemplo="Ej.: Departamento de 2 dormitorios en calle Los Pinos Nº 120, Santa Cruz de la Sierra"),
            Campo("canon", "Canon de arrendamiento y moneda", ejemplo="Ej.: 2.500 bolivianos por mes"),
            Campo("plazo", "Plazo del contrato", ejemplo="Ej.: 12 meses desde el 1 de octubre de 2026"),
            Campo("dia_pago", "Día de pago del canon", obligatorio=False, ejemplo="Ej.: El día 5 de cada mes (opcional)"),
            Campo("destino", "Destino o uso del inmueble", obligatorio=False, ejemplo="Ej.: Vivienda familiar (opcional)"),
        ),
        clausulas=("OBJETO", "CANON Y FORMA DE PAGO", "PLAZO", "DESTINO DEL INMUEBLE",
                   "OBLIGACIONES DE LAS PARTES", "CONFORMIDAD"),
        consulta_normativa="arrendamiento canon plazo obligaciones arrendador arrendatario",
    ),
    TipoDocumento.PRESTAMO: Plantilla(
        tipo=TipoDocumento.PRESTAMO,
        titulo="CONTRATO DE PRÉSTAMO",
        campos=(
            Campo("prestamista_nombre", "Nombre completo de quien presta", ejemplo="Ej.: Juan Carlos Pérez Gómez"),
            Campo("prestamista_ci", "Documento de identidad de quien presta", ejemplo="Ej.: 4587963"),
            Campo("prestatario_nombre", "Nombre completo de quien recibe el préstamo", ejemplo="Ej.: María Fernanda López Rivero"),
            Campo("prestatario_ci", "Documento de identidad de quien recibe", ejemplo="Ej.: 7845126"),
            Campo("lugar", "Lugar de suscripción", ejemplo="Ej.: Santa Cruz de la Sierra (sin siglas)"),
            Campo("fecha", "Fecha de suscripción", ejemplo="Ej.: 1 de octubre de 2026 (con día, mes y año)"),
            Campo("monto", "Monto prestado y moneda", ejemplo="Ej.: 25.000 bolivianos"),
            Campo("plazo_devolucion", "Plazo o fecha de devolución", ejemplo="Ej.: 12 meses, hasta el 30 de septiembre de 2027"),
            Campo("interes", "Interés convenido, si lo hay", obligatorio=False, ejemplo="Ej.: 2% mensual (vacío si no hay interés)"),
            Campo("garantia", "Garantía ofrecida, si la hay", obligatorio=False, ejemplo="Ej.: Un vehículo en prenda (vacío si no hay garantía)"),
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
