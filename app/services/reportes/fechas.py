"""De "este mes" a un rango concreto.

El modelo solo puede nombrar una expresión de esta lista o escribir una fecha ISO; quien
la convierte en un rango real es el backend. Así "septiembre" no depende de lo que el
modelo crea que es hoy, y una expresión que no esté aquí se rechaza en vez de resolverse
con una fecha inventada.

Todo rango es [inicio, fin): el fin queda fuera, que es lo correcto para comparar
instantes con hora.
"""
import re
import unicodedata
from datetime import datetime, timedelta, timezone

# Bolivia no aplica horario de verano, así que el desfase es fijo y exacto. Sin esto
# "hoy" se cortaría a las 20:00 locales, que es la medianoche UTC.
ZONA_BOLIVIA = timezone(timedelta(hours=-4))

MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
         "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
         "noviembre": 11, "diciembre": 12}

RELATIVAS = ("hoy", "ayer", "esta_semana", "semana_pasada", "este_mes", "mes_pasado",
             "este_anio", "anio_pasado", "ultimos_7_dias", "ultimos_30_dias",
             "ultimos_90_dias", "ultimos_12_meses")


class FechaAmbigua(ValueError):
    """La expresión no se puede convertir en un rango sin suponer nada."""


def _normalizar(valor: str) -> str:
    plano = unicodedata.normalize("NFKD", (valor or "").strip().lower())
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    plano = re.sub(r"\b(de|del|el|la|los|las|en)\b", " ", plano)
    return re.sub(r"[\s\-/]+", "_", plano).strip("_")


def _inicio_de_dia(momento: datetime) -> datetime:
    return momento.astimezone(ZONA_BOLIVIA).replace(hour=0, minute=0, second=0, microsecond=0)


def _sumar_meses(momento: datetime, meses: int) -> datetime:
    total = momento.month - 1 + meses
    return momento.replace(year=momento.year + total // 12, month=total % 12 + 1, day=1)


def _mes(anio: int, mes: int) -> tuple[datetime, datetime]:
    inicio = datetime(anio, mes, 1, tzinfo=ZONA_BOLIVIA)
    return inicio, _sumar_meses(inicio, 1)


def resolver(expresion: str, ahora: datetime | None = None) -> tuple[datetime, datetime]:
    """Devuelve [inicio, fin) en UTC. Lanza FechaAmbigua si no es interpretable."""
    ahora = (ahora or datetime.now(timezone.utc)).astimezone(ZONA_BOLIVIA)
    hoy = _inicio_de_dia(ahora)
    texto = _normalizar(expresion)
    if not texto:
        raise FechaAmbigua("Falta la fecha")

    rango = _relativa(texto, hoy)
    if rango is None:
        rango = _absoluta(texto, hoy)
    if rango is None:
        raise FechaAmbigua(expresion)
    inicio, fin = rango
    return inicio.astimezone(timezone.utc), fin.astimezone(timezone.utc)


def _relativa(texto: str, hoy: datetime) -> tuple[datetime, datetime] | None:
    if texto == "hoy":
        return hoy, hoy + timedelta(days=1)
    if texto == "ayer":
        return hoy - timedelta(days=1), hoy
    if texto in ("esta_semana", "semana_actual"):
        lunes = hoy - timedelta(days=hoy.weekday())
        return lunes, lunes + timedelta(days=7)
    if texto in ("semana_pasada", "semana_anterior"):
        lunes = hoy - timedelta(days=hoy.weekday() + 7)
        return lunes, lunes + timedelta(days=7)
    if texto in ("este_mes", "mes_actual"):
        return _mes(hoy.year, hoy.month)
    if texto in ("mes_pasado", "mes_anterior"):
        anterior = _sumar_meses(hoy, -1)
        return _mes(anterior.year, anterior.month)
    if texto in ("este_anio", "este_ano", "anio_actual", "ano_actual"):
        return datetime(hoy.year, 1, 1, tzinfo=ZONA_BOLIVIA), datetime(hoy.year + 1, 1, 1,
                                                                       tzinfo=ZONA_BOLIVIA)
    if texto in ("anio_pasado", "ano_pasado", "anio_anterior", "ano_anterior"):
        return datetime(hoy.year - 1, 1, 1, tzinfo=ZONA_BOLIVIA), datetime(hoy.year, 1, 1,
                                                                           tzinfo=ZONA_BOLIVIA)
    dias = re.fullmatch(r"ultimos?_(\d{1,3})_dias", texto)
    if dias:
        return hoy - timedelta(days=int(dias.group(1))), hoy + timedelta(days=1)
    meses = re.fullmatch(r"ultimos?_(\d{1,2})_meses", texto)
    if meses:
        return _sumar_meses(hoy, -int(meses.group(1))), hoy + timedelta(days=1)
    return None


def _absoluta(texto: str, hoy: datetime) -> tuple[datetime, datetime] | None:
    iso = re.fullmatch(r"(\d{4})_(\d{1,2})_(\d{1,2})", texto)
    if iso:
        dia = datetime(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)),
                       tzinfo=ZONA_BOLIVIA)
        return dia, dia + timedelta(days=1)
    anio_mes = re.fullmatch(r"(\d{4})_(\d{1,2})", texto)
    if anio_mes:
        return _mes(int(anio_mes.group(1)), int(anio_mes.group(2)))
    solo_anio = re.fullmatch(r"(\d{4})", texto)
    if solo_anio:
        anio = int(solo_anio.group(1))
        return (datetime(anio, 1, 1, tzinfo=ZONA_BOLIVIA),
                datetime(anio + 1, 1, 1, tzinfo=ZONA_BOLIVIA))

    nombre_anio = re.fullmatch(r"([a-z]+)_(\d{4})", texto)
    if nombre_anio and nombre_anio.group(1) in MESES:
        return _mes(int(nombre_anio.group(2)), MESES[nombre_anio.group(1)])
    if texto in MESES:
        # Un mes suelto es el más reciente que ya empezó: en septiembre "marzo" es el de
        # este año y "noviembre" el del anterior. Es una regla fija, no una suposición
        # sobre lo que el usuario quiso decir.
        mes = MESES[texto]
        anio = hoy.year if mes <= hoy.month else hoy.year - 1
        return _mes(anio, mes)
    return None


def describir(expresion: str, inicio: datetime, fin: datetime) -> str:
    """Cómo se le muestra al usuario el rango que realmente se aplicó."""
    local_inicio = inicio.astimezone(ZONA_BOLIVIA)
    local_fin = (fin - timedelta(seconds=1)).astimezone(ZONA_BOLIVIA)
    if local_inicio.date() == local_fin.date():
        return f"{expresion} ({local_inicio:%d/%m/%Y})"
    return f"{expresion} (del {local_inicio:%d/%m/%Y} al {local_fin:%d/%m/%Y})"
