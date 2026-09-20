"""Recuperación dentro de UN documento.

Cuando la pregunta es sobre un contrato concreto no sirve la búsqueda normativa: hay que
mirar ese documento y solo ese. Este módulo parte el texto en fragmentos y elige los que
tienen que ver con la pregunta, para no mandarle cien páginas al modelo.

El corte reutiliza el segmentador de cláusulas que ya usa el análisis contractual, así
que un fragmento coincide con una cláusula real del documento y se puede citar por su
nombre («Cláusula QUINTA») en lugar de por un número inventado.

El alcance queda fijado por quien llama: acá nunca se resuelve a qué documento pertenece
un texto ni de quién es. El dueño se comprueba antes, en el controlador.
"""
from dataclasses import dataclass
import re

from app.services.documentos.segmentador_clausulas import segmentar
from app.services.shared.normalizacion import normalizar, tokenizar

# Presupuesto de texto que se le manda al modelo. Un documento que entra entero se manda
# entero: partirlo solo agregaría el riesgo de dejar afuera la parte que responde.
PRESUPUESTO_CARACTERES = 6000
MAXIMO_FRAGMENTOS = 6
# Una cláusula corta sigue siendo una cláusula: «El plazo es de doce (12) meses.» son
# 31 caracteres y es exactamente lo que alguien va a preguntar. El mínimo solo existe
# para descartar líneas vacías o un encabezado suelto, no contenido breve.
MINIMO_CARACTERES_CLAUSULA = 12
# En el corte por ventanas el último trozo sí puede ser basura, y ahí sí conviene exigir
# algo de cuerpo.
MINIMO_CARACTERES_VENTANA = 40
# Cuando no hay cláusulas reconocibles se corta por tamaño, con solape para no partir
# una frase justo donde estaba la respuesta.
VENTANA = 1200
SOLAPE = 150


@dataclass(frozen=True)
class FragmentoDocumento:
    """Un trozo del documento, con la etiqueta con la que se lo cita."""
    etiqueta: str
    texto: str
    orden: int
    relevancia: float = 0.0


def _por_ventanas(texto: str) -> list[FragmentoDocumento]:
    fragmentos = []
    inicio = 0
    while inicio < len(texto):
        fin = min(inicio + VENTANA, len(texto))
        trozo = texto[inicio:fin].strip()
        if len(trozo) >= MINIMO_CARACTERES_VENTANA:
            fragmentos.append(FragmentoDocumento(
                etiqueta=f"Fragmento {len(fragmentos) + 1}", texto=trozo,
                orden=len(fragmentos)))
        if fin >= len(texto):
            break
        inicio = fin - SOLAPE
    return fragmentos


def fragmentar(texto: str) -> list[FragmentoDocumento]:
    """El documento partido en piezas citables: por cláusula si las tiene, si no por tamaño."""
    if not (texto or "").strip():
        return []
    clausulas = segmentar(texto)
    fragmentos = [
        FragmentoDocumento(
            etiqueta=(f"Cláusula {c.ordinal}" if c.ordinal else (c.encabezado or f"Sección {i + 1}")),
            texto=c.texto.strip(), orden=i)
        for i, c in enumerate(clausulas)
        if len(c.texto.strip()) >= MINIMO_CARACTERES_CLAUSULA
    ]
    # Un documento sin cláusulas numeradas (una carta, un acta) igual tiene que poder
    # consultarse: se cae a ventanas de tamaño fijo.
    return fragmentos or _por_ventanas(texto)


SENALES = {
    "partes": ("partes", "comparecen", "intervienen", "prestamista", "prestatario",
               "vendedor", "comprador", "arrendador", "arrendatario"),
    "plazo": ("plazo", "duracion", "vigencia", "meses", "fecha final", "vencimiento"),
    "monto": ("monto", "precio", "capital", "canon", "suma", "bs", "usd"),
    "fecha": ("fecha", "inicio", "comienza", "final", "vencimiento", "firma"),
    "firma": ("firma", "firman", "suscriben"),
}


def intencion_documental(pregunta: str) -> str | None:
    plano = normalizar(pregunta)
    if re.search(r"\b(?:quienes|partes|comparecen|intervienen)\b", plano):
        return "partes"
    if re.search(r"\b(?:cuanto|monto|precio|capital|canon)\b", plano):
        return "monto"
    if re.search(r"\b(?:plazo|duracion|vigencia)\b", plano):
        return "plazo"
    if re.search(r"\b(?:quien firma|quienes firman|firmantes)\b", plano):
        return "firma"
    if re.search(r"\b(?:cuando|fecha|vence|vencimiento|empieza|comienza|termina)\b", plano):
        return "fecha"
    return None


def _puntuar(fragmento: FragmentoDocumento, terminos: set[str], frase: str,
             intencion: str | None = None) -> float:
    plano = normalizar(fragmento.texto)
    palabras = set(tokenizar(fragmento.texto))
    if not terminos:
        return 0.0
    comunes = terminos & palabras
    # Proporción de la pregunta cubierta, no cantidad bruta: si no, gana el fragmento
    # más largo por el solo hecho de tener más palabras.
    puntaje = len(comunes) / len(terminos)
    # Que aparezca la frase entera es una señal mucho más fuerte que palabras sueltas.
    if len(frase) >= 12 and frase in plano:
        puntaje += 1.0
    if intencion:
        senales = SENALES[intencion]
        presentes = sum(bool(re.search(r"\b" + re.escape(s) + r"\b", plano))
                        for s in senales)
        puntaje += min(presentes, 3) * 0.3
        # Una clausula dedicada al tema suele ser evidencia mas directa que firmas.
        encabezado = normalizar(fragmento.etiqueta + " " + fragmento.texto[:100])
        if any(s in encabezado for s in senales[:3]):
            puntaje += 0.25
    return puntaje


def recuperar(texto_documento: str, pregunta: str,
              presupuesto: int = PRESUPUESTO_CARACTERES) -> list[FragmentoDocumento]:
    """Los fragmentos del documento que pueden responder la pregunta, en orden de lectura.

    Si el documento entra completo en el presupuesto se devuelve entero. Si no, se
    puntúa cada fragmento contra la pregunta y se devuelven los mejores, reordenados
    como aparecen en el documento para que la respuesta se lea coherente.
    """
    fragmentos = fragmentar(texto_documento)
    if not fragmentos:
        return []

    terminos = set(tokenizar(pregunta))
    frase = normalizar(pregunta)
    intencion = intencion_documental(pregunta)
    puntuados = sorted(
        (FragmentoDocumento(f.etiqueta, f.texto, f.orden,
                            _puntuar(f, terminos, frase, intencion))
         for f in fragmentos),
        key=lambda f: (-f.relevancia, f.orden))

    total = sum(len(f.texto) for f in fragmentos)
    if total <= presupuesto:
        # Mantiene el documento completo, pero el fragmento mas directo llega primero.
        return puntuados

    elegidos: list[FragmentoDocumento] = []
    usados = 0
    for fragmento in puntuados:
        if len(elegidos) >= MAXIMO_FRAGMENTOS or usados + len(fragmento.texto) > presupuesto:
            continue
        elegidos.append(fragmento)
        usados += len(fragmento.texto)

    # Sin coincidencias no se devuelve vacío: el principio del documento suele traer las
    # partes y el objeto, y es mejor eso que no poder responder nada.
    if not elegidos:
        elegidos = [f for f in fragmentos[:2] if len(f.texto) <= presupuesto]
    return elegidos
