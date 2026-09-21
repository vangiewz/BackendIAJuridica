"""Revisión de los datos del formulario ANTES de pedirle nada al modelo.

Es determinista (sin IA) e instantánea, y responde una sola pregunta: «¿qué campo escribió mal el
usuario y cómo se arregla?». Sirve para dos cosas:

  - al interpretar una descripción, mostrar de inmediato que un campo quedó con algo que no sirve
    («hoy» en la fecha, una sigla como «SCZ» en el lugar);
  - al generar, negarse a redactar con datos que se sabe que no van a funcionar y decir cuáles son.

Es CONSERVADORA a propósito: solo marca como `error` lo que sin duda no sirve (una fecha que es «hoy»,
un documento de identidad sin números). Lo dudoso es un `aviso`, que se muestra pero no impide generar.
Un falso error bloquearía a alguien que escribió bien, y eso es peor que dejar pasar un dato dudoso.
"""
import re
from dataclasses import dataclass

from app.services.generacion.plantillas import Plantilla
from app.services.ia.validacion import sin_acentos

ERROR = "error"
AVISO = "aviso"


@dataclass(frozen=True)
class Problema:
    clave: str
    etiqueta: str
    mensaje: str
    ejemplo: str
    nivel: str


MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "setiembre", "octubre", "noviembre", "diciembre")
FECHA_RELATIVA = re.compile(
    r"\b(hoy|manana|ayer|ahora|actual|cualquiera|la de hoy|hoy dia|no se|n/?a|pendiente|a definir)\b")
NUMEROS_EN_PALABRAS = re.compile(
    r"\b(un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|quince|veinte|treinta|"
    r"cuarenta|cincuenta|sesenta|setenta|ochenta|noventa|cien|ciento|mil|millon|millones|medio)\b")
UNIDADES_DE_TIEMPO = re.compile(r"\b(dia|dias|semana|semanas|mes|meses|ano|anos|trimestre|semestre)\b")
MONEDA = re.compile(r"(\bbs\b|bs\.|boliviano|\$|\bus\b|\bsus\b|usd|dolar|euro)")
# Preposiciones y artículos que pueden ir en mayúsculas dentro de un lugar escrito en mayúsculas.
PALABRAS_CORTAS = {"de", "del", "la", "las", "el", "los", "y", "en", "san", "santa"}

SIGLAS_DE_CIUDAD = {
    "scz": "Santa Cruz de la Sierra", "lpz": "La Paz", "cbba": "Cochabamba", "cbb": "Cochabamba",
    "oru": "Oruro", "sre": "Sucre", "tja": "Tarija", "pts": "Potosí", "tdd": "Trinidad", "cij": "Cobija",
}


def _sin_prefijo(ejemplo: str) -> str:
    return re.sub(r"^\s*Ej\.?:?\s*", "", ejemplo or "").strip()


def _plano(valor: str) -> str:
    return sin_acentos(valor).lower()


def _revisar_nombre(valor: str) -> str | None:
    if re.search(r"\d", valor):
        return "El nombre no debe llevar números."
    palabras = re.findall(r"[^\W\d_]+", valor)
    if len(palabras) < 2:
        return "Escribí el nombre y el apellido completos."
    return None


def _revisar_documento(valor: str) -> str | None:
    numeros = re.sub(r"\D", "", valor)
    if len(numeros) < 5:
        return "El número de documento debe tener al menos 5 dígitos."
    if len(numeros) > 12:
        return "El número de documento tiene demasiados dígitos."
    return None


def _revisar_fecha(valor: str) -> tuple[str, str] | None:
    plano = _plano(valor)
    if "fecha de suscripcion" in plano or "fecha" in plano.split()[:1]:
        return ERROR, "Escribí solo la fecha, sin el texto «fecha de suscripción»."
    if FECHA_RELATIVA.search(plano):
        return ERROR, "Eso no es una fecha. Escribí el día, el mes y el año."
    tiene_mes = any(mes in plano for mes in MESES)
    if not re.search(r"\d", plano) and not tiene_mes:
        return ERROR, "Escribí la fecha con día, mes y año."
    tiene_anio = bool(re.search(r"\b\d{4}\b", plano)) or bool(re.search(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", plano))
    if not tiene_anio:
        return AVISO, "Falta el año de la fecha."
    return None


def _revisar_lugar(valor: str) -> tuple[str, str] | None:
    plano = _plano(valor)
    mensajes: list[str] = []
    if "lugar de suscripcion" in plano or plano.split()[:1] == ["lugar"]:
        mensajes.append("Escribí solo el lugar, sin el texto «lugar de suscripción».")
    palabras = re.findall(r"[^\W\d_]+", valor)
    hay_minusculas = any(letra.islower() for letra in valor)
    for palabra in palabras:
        letras = sin_acentos(palabra)
        if not (2 <= len(letras) <= 5 and palabra.isupper()) or letras.lower() in PALABRAS_CORTAS:
            continue
        # «SANTA CRUZ» entero en mayúsculas es un lugar válido; «SCZ» suelta, o mezclada con
        # minúsculas, es una sigla que el modelo tendría que adivinar.
        if hay_minusculas or len(palabras) == 1:
            sugerencia = SIGLAS_DE_CIUDAD.get(letras.lower())
            sugerido = f" Escribí «{sugerencia}»." if sugerencia else " Escribí el nombre completo del lugar."
            mensajes.append(f"«{palabra}» es una sigla.{sugerido}")
            break
    # Una sigla o el texto de la etiqueta afean el contrato pero no lo invalidan: se avisa, no se bloquea.
    return (AVISO, " ".join(mensajes)) if mensajes else None


def _revisar_monto(valor: str) -> tuple[str, str] | None:
    plano = _plano(valor)
    if not re.search(r"\d", plano) and not NUMEROS_EN_PALABRAS.search(plano):
        return ERROR, "Escribí el monto con números."
    if not MONEDA.search(plano):
        return AVISO, "Falta la moneda (por ejemplo: bolivianos)."
    return None


def _revisar_plazo(valor: str) -> str | None:
    plano = _plano(valor)
    hay_numero = re.search(r"\d", plano) or NUMEROS_EN_PALABRAS.search(plano)
    if not (hay_numero or UNIDADES_DE_TIEMPO.search(plano) or any(m in plano for m in MESES)):
        return "Indicá el plazo con un número y una unidad, por ejemplo: 12 meses."
    return None


def _un_problema(campo, nivel: str, mensaje: str) -> Problema:
    return Problema(clave=campo.clave, etiqueta=campo.etiqueta, mensaje=mensaje,
                    ejemplo=_sin_prefijo(campo.ejemplo), nivel=nivel)


def revisar_datos(plantilla: Plantilla, datos: dict) -> list[Problema]:
    """Los campos cargados que sin duda no sirven (`error`) o que probablemente den problemas (`aviso`).

    Solo mira lo que está escrito: un campo vacío no es un problema (queda marcado como pendiente).
    """
    problemas: list[Problema] = []
    for campo in plantilla.campos:
        valor = str(datos.get(campo.clave, "") or "").strip()
        if not valor:
            continue
        veredicto: tuple[str, str] | None = None
        clave = campo.clave
        if not re.search(r"[^\W_]", valor):
            veredicto = (ERROR, "No escribiste nada legible en este campo.")
        elif len(valor) > 400:
            veredicto = (AVISO, "El texto es muy largo; resumilo en una o dos frases.")
        elif clave.endswith("_nombre"):
            mensaje = _revisar_nombre(valor)
            veredicto = (ERROR, mensaje) if mensaje else None
        elif clave.endswith("_ci"):
            mensaje = _revisar_documento(valor)
            veredicto = (ERROR, mensaje) if mensaje else None
        elif clave == "fecha":
            veredicto = _revisar_fecha(valor)
        elif clave == "lugar":
            veredicto = _revisar_lugar(valor)
        elif clave in ("monto", "precio", "canon"):
            veredicto = _revisar_monto(valor)
        elif clave in ("plazo", "plazo_devolucion"):
            mensaje = _revisar_plazo(valor)
            veredicto = (ERROR, mensaje) if mensaje else None
        if veredicto:
            problemas.append(_un_problema(campo, *veredicto))
    return problemas


def errores(problemas: list[Problema]) -> list[Problema]:
    return [p for p in problemas if p.nivel == ERROR]
