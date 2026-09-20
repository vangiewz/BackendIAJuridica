"""Vocabulario de búsqueda explicable. No contiene artículos ni conclusiones legales."""
import re
from app.services.shared.normalizacion import normalizar

# Traduce expresiones coloquiales a conceptos de recuperación. No cambia el clasificador.
# Solo se activa sobre expresiones presentes; nunca convierte estos conceptos en hechos.
# Los disparadores usan raíces («alquil», «arrend», «desocup») porque el usuario escribe
# «alquilo», «alquilé» o «desocupe» y una lista de formas exactas dejaba fuera la consulta.
PATRONES = (
    (r"\bresponsabilidad\s+contractual\b",
     "responsabilidad contractual incumplimiento obligacion deudor mora resarcimiento dano perjuicios cumplimiento"),
    (r"\b(?:alquil\w*|arrend\w*|inquilin\w*|locatari\w*)\b",
     "arrendamiento arrendatario arrendador locacion"),
    (r"\b(?:alquil\w*|arrend\w*|inquilin\w*)\b.{0,400}\b(?:vend\w*|venta|enajen\w*|transferir|nuevo dueno|nuevo propietario)\b"
     r"|\b(?:vend\w*|venta|enajen\w*)\b.{0,400}\b(?:alquil\w*|arrend\w*|inquilin\w*)\b",
     "enajenacion cosa arrendada adquirente respetar arrendamiento"),
    (r"\b(?:alquil\w*|arrend\w*|inquilin\w*)\b.{0,400}\b(?:termin\w*|desocup\w*|desaloj\w*|echar|irme|devolver el inmueble|resolver el contrato)\b"
     r"|\b(?:termin\w*|desocup\w*|desaloj\w*)\b.{0,400}\b(?:alquil\w*|arrend\w*|inquilin\w*)\b",
     "extincion arrendamiento vencimiento plazo desahucio restitucion"),
    (r"\b(?:alquil\w*|arrend\w*|inquilin\w*)\b.{0,400}\b(?:un ano|dos anos|plazo|duracion|por un|contrato por)\b",
     "duracion arrendamiento plazo termino convenido"),
    (r"\b(?:compre|compraventa|comprador|vendedor)\b",
     "venta vendedor comprador obligaciones entrega transferencia"),
    (r"\bsin\s+testamento\b", "sucesion legal herencia"),
    (r"\b(?:padre|madre|papa|mama)\b.{0,50}\b(?:fallecio|murio)\b",
     "sucesion hijos descendientes"),
    (r"\b(?:me debe|deuda|deudor|acreedor)\b", "obligacion deudor acreedor pago cumplimiento"),
    (r"(?:vencio el plazo|venci[oó] el termino|no me paga|no paga|se atraso|esta atrasad)",
     "mora requerimiento intimacion retraso incumplimiento resarcimiento"),
    (r"\b(?:preste|prestamo|prestamos|prestado|prestada)\b",
     "prestamo mutuo restitucion deudor acreedor obligacion"),
    (r"\b(?:repartir|reparto|particion|dividir la|division de)\b.{0,40}\b(?:casa|bienes|herencia|terreno)\b",
     "particion division herencia coherederos comunidad"),
    (r"\b(?:dano|dano mi|dano su|danaron|danada|perjuicio|reparacion del dano)\b",
     "responsabilidad hecho ilicito resarcimiento dano"),
    (r"\bservidumbre\b", "servidumbre paso ejercicio"),
)


def expandir_consulta(consulta: str) -> tuple[str, list[str]]:
    """Devuelve el texto para el canal léxico y los conceptos reconocidos.

    El texto conserva SIEMPRE la consulta original: reemplazarla por los conceptos
    perdía los términos centrales del usuario («alquiler», «venderlo») y el ranking
    terminaba en normas laterales de cobro o de daños. Los conceptos se agregan
    detrás como vocabulario auxiliar, y son además la señal temática que usa el
    reordenamiento final de la búsqueda híbrida.
    """
    normalized = normalizar(consulta)
    terms = [concept for pattern, concept in PATRONES if re.search(pattern, normalized)]
    if not terms:
        return consulta, terms
    conceptos = ' '.join(dict.fromkeys(' '.join(terms).split()))
    return f"{consulta} {conceptos}", terms
