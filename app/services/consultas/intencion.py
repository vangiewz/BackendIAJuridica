"""Qué quiere hacer el usuario cuando hay un documento adjunto.

Se resuelve con reglas léxicas, sin llamar al modelo: distinguir «guardalo» de
«analizalo» de «¿cuál es el plazo?» no necesita treinta segundos de Qwen, y una
clasificación determinista es la que permite prometer que subir un archivo nunca
dispara un análisis que nadie pidió.

Sin documento activo todo es consulta general: el flujo jurídico existente no cambia.
"""
import re
from enum import Enum

from app.services.shared.normalizacion import normalizar


class Intencion(str, Enum):
    CONSULTA_GENERAL = "consulta_general"
    GUARDAR_DOCUMENTO = "guardar_documento"
    ANALIZAR_DOCUMENTO = "analizar_documento"
    CONSULTA_DOCUMENTO = "consulta_documento"
    CONSULTA_DOCUMENTO_NORMATIVA = "consulta_documento_normativa"


# Guardar y nada más. "guarda" cubre guardalo/guardala/guardar/guardame.
GUARDAR = (r"\bguard", r"\bsolo\s+(?:lo\s+)?sub", r"\bsubilo\b", r"\balmacen")

# Pedido explícito del análisis contractual completo.
ANALIZAR = (r"\banaliz", r"\brevisa(?:lo|me|r)?\s+(?:el|este|mi)\b",
            r"\bhac[ée]\s+el\s+an[aá]lisis\b", r"\bdetect[aá]\s+(?:los\s+)?riesgos\b")

# Señales de que la pregunta mira a la normativa y no solo al papel.
NORMATIVA = (r"\bc[oó]digo\s+civil\b", r"\bnormativa\b", r"\bnorma\b", r"\bley\b",
             r"\bleyes\b", r"\bart[ií]culo\b", r"\blegal(?:mente)?\b", r"\bl[eí]cit",
             r"\bpermite\s+la\s+ley\b", r"\bseg[uú]n\s+la\s+ley\b", r"\bes\s+v[aá]lid",
             r"\bderecho\s+boliviano\b", r"\bjur[ií]dicamente\b", r"\bcorresponde\s+legal")

# Señales de que la pregunta habla del documento que está adjunto.
REFERENCIA_DOCUMENTO = (
    r"\beste\s+(?:documento|contrato|archivo|papel|acuerdo)\b",
    r"\bel\s+(?:documento|contrato|archivo|acuerdo)\b",
    r"\bmi\s+(?:documento|contrato|archivo|acuerdo)\b",
    r"\besta\s+cl[aá]usula\b", r"\bla\s+cl[aá]usula\b", r"\bcl[aá]usula\s+\w+",
    r"\bque\s+sub[ií]\b", r"\bac[aá]\b", r"\baqu[ií]\b",
    r"\bdel\s+(?:documento|contrato)\b", r"\ben\s+el\s+(?:documento|contrato)\b",
)


def _coincide(patrones, texto: str) -> bool:
    return any(re.search(patron, texto) for patron in patrones)


def detectar(texto: str, hay_documento: bool) -> Intencion:
    """La intención de la frase. `hay_documento` decide si las demás opciones existen."""
    if not hay_documento:
        return Intencion.CONSULTA_GENERAL

    plano = normalizar(texto or "")
    pregunta = "?" in (texto or "")

    # Una pregunta nunca es una orden de guardar ni de analizar, aunque nombre el verbo
    # ("¿me conviene analizarlo?" no lanza el análisis).
    if not pregunta:
        if _coincide(ANALIZAR, plano):
            return Intencion.ANALIZAR_DOCUMENTO
        if _coincide(GUARDAR, plano):
            return Intencion.GUARDAR_DOCUMENTO

    menciona_normativa = _coincide(NORMATIVA, plano)
    menciona_documento = _coincide(REFERENCIA_DOCUMENTO, plano)

    if menciona_normativa:
        # "¿Qué dice el Código Civil sobre arrendamiento?" sigue siendo una consulta
        # general aunque haya un contrato abierto: no nombra el documento.
        return (Intencion.CONSULTA_DOCUMENTO_NORMATIVA if menciona_documento
                else Intencion.CONSULTA_GENERAL)
    return Intencion.CONSULTA_DOCUMENTO


def usa_documento(intencion: Intencion) -> bool:
    return intencion in (Intencion.CONSULTA_DOCUMENTO,
                         Intencion.CONSULTA_DOCUMENTO_NORMATIVA)
