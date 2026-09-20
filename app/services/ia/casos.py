"""Cobertura de relatos: conceptos de búsqueda y hechos literales, sin conclusiones legales."""
from dataclasses import dataclass
import re
from decimal import Decimal
from datetime import date
from types import MappingProxyType

from app.services.shared.normalizacion import normalizar


@dataclass(frozen=True)
class BusquedaProblema:
    clave: str
    consulta: str
    requisitos: tuple[str, ...]
    foco: str

    def pertinente(self, norma) -> bool:
        texto = normalizar(f"{norma.epigrafe or ''} {norma.texto}")
        return all(re.search(patron, texto) for patron in self.requisitos)

    def prioridad(self, norma) -> int:
        return int(bool(re.search(self.foco, normalizar(norma.epigrafe or ""))))


@dataclass(frozen=True)
class ProblemaCaso:
    clave: str
    titulo: str
    patron: str
    busquedas: tuple[BusquedaProblema, ...]


PROBLEMAS = (
    ProblemaCaso("pago", "Falta de pago y responsabilidad contractual",
        r"no pag|falta de pago|incumpl|responsabilidad contractual", (
        BusquedaProblema("pago", "arrendatario pagar canon plazos convenidos", (r"arrendatario", r"canon", r"paga"), r"obligaciones principales"),
        BusquedaProblema("responsabilidad", "responsabilidad deudor incumplimiento resarcimiento", (r"deudor", r"no cumple|incumpl", r"resarc"), r"responsabilidad del deudor"))),
    ProblemaCaso("mora", "Requerimiento y mora", r"requerimiento|intimacion|\bmora\b", (
        BusquedaProblema("mora", "constitucion mora intimacion requerimiento deudor", (r"deudor", r"mora", r"requerimiento"), r"constitucion en mora"),)),
    ProblemaCaso("resolucion", "Posible resolución del contrato", r"resolucion|resolver el contrato", (
        BusquedaProblema("resolucion", "resolucion incumplimiento contratos reciprocas", (r"contrato", r"resolucion", r"reciprocas"), r"incumplimiento"),
        BusquedaProblema("resolucion_requerimiento", "resolucion requerimiento nota notarialmente termino", (r"notarial", r"termino", r"contrato"), r"resolucion por requerimiento"))),
    ProblemaCaso("tercero", "Uso por un tercero", r"tercero|otra persona|subarrend|ceder el contrato", (
        BusquedaProblema("tercero", "subarrendar ceder contrato vivienda arrendatario", (r"arrendatario", r"subarrend", r"vivienda"), r"prohibicion de subarrendar"),)),
    ProblemaCaso("modificaciones", "Modificación no autorizada del inmueble", r"modific|pared|alteracion", (
        BusquedaProblema("modificaciones", "arrendatario cosa servirse uso destino diligencia", (r"arrendatario", r"servirse|uso", r"diligencia|destino"), r"obligaciones principales"),)),
    ProblemaCaso("danos", "Daños y su acreditación", r"\bdanos?\b|perjuicio|resarcimiento", (
        BusquedaProblema("danos", "resarcimiento dano incumplimiento perdida acreedor ganancia", (r"incumplimiento", r"perdida", r"acreedor"), r"resarcimiento del dano"),)),
    ProblemaCaso("penalidad", "Cláusula penal y posible exceso", r"penalidad|clausula penal|pena convencional", (
        BusquedaProblema("penalidad", "clausula penal resarcimiento convencional retraso", (r"clausula penal", r"sustituye"), r"resarcimiento convencional"),
        BusquedaProblema("pena_excesiva", "disminucion equitativa pena excesiva", (r"pena", r"excesiva|disminuida"), r"disminucion equitativa"),
        BusquedaProblema("pena_limite", "cuantia pena convencional obligacion principal", (r"pena convencional", r"exceder"), r"cuantia de la pena"))),
    ProblemaCaso("humedad", "Humedad y posible afectación del uso", r"humedad|filtracion|inhabitable|vicios", (
        BusquedaProblema("humedad", "arrendada vicios idoneidad uso goce canon", (r"arrendada", r"vicios", r"idoneidad"), r"vicios"),
        BusquedaProblema("reparaciones", "arrendador mantener cosa reparaciones necesarias", (r"arrendador", r"reparaciones", r"mantener"), r"mantenimiento"))),
    ProblemaCaso("pruebas", "Pruebas relevantes", r"prueba|fotograf|testimonio|comprobantes|whatsapp", (
        BusquedaProblema("pruebas", "carga prueba hechos pretension excepcion", (r"probar", r"pretension", r"excepcion"), r"carga de la prueba"),)),
)


@dataclass(frozen=True)
class ProblemaDetectado:
    """Un problema jurídico del caso y los términos con que buscar su norma.

    Lo produce el modelo al descomponer el relato. No condiciona ninguna garantía: de él
    solo salen términos de búsqueda, y toda norma que llegue al usuario viene del corpus
    y pasa por la validación de citas de siempre.
    """
    clave: str
    titulo: str
    consulta: str
    pregunta: str = ""
    familia: str = ""


# Las familias son conceptos jurídicos y ámbitos contractuales; nunca IDs de artículos.
# La condición sobre el epígrafe evita que una coincidencia léxica de mandato, venta o
# simulación termine apoyando un apartado sobre una obra o un contrato recíproco.
TEMAS = (
    ("acumulacion", r"coexist|acumul|penal.*(?:gasto|da[nñ]o)|(?:gasto|da[nñ]o).*penal", "Cláusula penal y gasto adicional",
     "pena convencional resarcimiento retraso danos adicionales obligacion", r"resarcimiento convencional|prohibicion de exigencia conjunta|^resarcimiento del dano$"),
    ("saldo", r"saldo|pendiente|restante|contraprestacion", "Saldo pendiente y cumplimiento recíproco",
     "excepcion incumplimiento contratos prestaciones reciprocas cumplimiento parcial", r"excepcion del incumplimiento|cumplimiento parcial"),
    ("vicios", r"vicios|defect|filtracion|ceramicas|obra.*calidad", "Vicios y defectos de la obra",
     "responsabilidad vicios falta cualidades obra contratista recepcion", r"vicios.*obra|obra.*vicios|recepcion de obra afectada"),
    ("proveedor", r"proveedor|causa no imputable|causa ajena", "Problema del proveedor e imputabilidad",
     "responsabilidad deudor que no cumple imposibilidad causa no imputable", r"responsabilidad del deudor que no cumple|incumplimiento por imposibilidad"),
    ("plazo", r"plazo adicional|dias adicionales|efecto.*plazo|requerimiento", "Efecto del plazo adicional",
     "resolucion requerimiento termino razonable intimacion mora", r"resolucion por requerimiento|constitucion en mora"),
    ("mora", r"\bmora\b|retras|vencim|no entreg|no pag|incumplimiento", "Mora e incumplimiento",
     "constitucion en mora vencimiento incumplimiento deudor", r"constitucion en mora|mora sin intimacion|responsabilidad del deudor que no cumple"),
    ("penalidad", r"penalidad|clausula penal|pena convencional|0[,.]5%", "Cláusula penal y su límite",
     "resarcimiento convencional cuantia pena disminucion equitativa", r"resarcimiento convencional|cuantia de la pena|disminucion equitativa"),
    ("resolucion", r"resolucion|resolv|terminar contrato", "Posible resolución del contrato",
     "resolucion incumplimiento contrato reciproco gravedad", r"^resolucion por incumplimiento$|^resolucion por requerimiento$|gravedad e importancia"),
    ("danos", r"\bdanos?\b|gasto adicional|resarcimiento", "Daños y gastos de reparación",
     "resarcimiento dano por incumplimiento contractual perdida acreedor", r"resarcimiento del dano|responsabilidad del deudor que no cumple"),
    ("informacion", r"informacion adicional|necesitari|que falta", "Información adicional necesaria",
     "", r"$^"),
)


def tema_de_pregunta(texto: str):
    plano = normalizar(texto)
    return next((tema for tema in TEMAS if re.search(tema[1], plano)), None)


def preguntas_numeradas(relato: str) -> list[str]:
    return [m.strip().rstrip('.') for m in re.findall(r"(?m)^\s*\d+[.)]\s+([^\n]+)", relato)]


def problemas_de_preguntas(relato: str) -> list[ProblemaDetectado]:
    problemas = []
    for indice, pregunta in enumerate(preguntas_numeradas(relato), 1):
        tema = tema_de_pregunta(pregunta)
        titulo = tema[2] if tema else pregunta[:80]
        consulta = tema[3] if tema else pregunta
        familia = tema[0] if tema else ""
        problemas.append(ProblemaDetectado(f"q{indice}", titulo, consulta, pregunta, familia))
    return problemas


def fuente_pertinente(problema: ProblemaDetectado, norma) -> bool:
    epigrafe = normalizar(norma.epigrafe or "")
    tema = next((t for t in TEMAS if t[0] == problema.familia), None)
    if tema:
        return bool(re.search(tema[4], epigrafe))
    # Para una cuestión nueva del modelo, exigir coincidencia sustantiva en el título y
    # que la norma pertenezca al mismo ámbito de la relación narrada.
    terminos = {p for p in re.findall(r"[a-z]{5,}", normalizar(problema.consulta))
                if p not in {"contrato", "derecho", "civil", "articulo", "normas"}}
    return len(terminos & set(re.findall(r"[a-z]{5,}", epigrafe))) >= 2


# Un relato corto con una sola pregunta no necesita el recorrido profundo; uno largo o con
# varias preguntas sí. El umbral es deliberadamente bajo: preferimos gastar tiempo de más
# antes que contestar un caso con varios problemas como si fuera uno solo.
MINIMO_CARACTERES_CASO = 400


def es_caso_complejo(relato: str) -> bool:
    if len(relato) >= MINIMO_CARACTERES_CASO:
        return True
    # Varias preguntas en un mismo mensaje ya son varios problemas que resolver.
    return relato.count("?") >= 2


def problemas_por_catalogo(relato: str) -> list[ProblemaDetectado]:
    """Respaldo determinista si el modelo no logra descomponer el caso."""
    plano = normalizar(relato)
    detectados = []
    for problema in PROBLEMAS:
        if re.search(problema.patron, plano):
            detectados.append(ProblemaDetectado(
                clave=problema.clave, titulo=problema.titulo,
                consulta=' '.join(b.consulta for b in problema.busquedas),
                familia=(tema[0] if (tema := tema_de_pregunta(problema.titulo)) else "")))
    presentes = {p.familia for p in detectados}
    for clave, patron, titulo, consulta, _ in TEMAS:
        if clave not in presentes and clave != "informacion" and re.search(patron, plano):
            detectados.append(ProblemaDetectado(clave, titulo, consulta, familia=clave))
            presentes.add(clave)
    return detectados


def problemas_del_caso(relato: str) -> list[ProblemaCaso]:
    plano = normalizar(relato)
    problemas = [p for p in PROBLEMAS if re.search(p.patron, plano)]
    # Una definición o una pregunta de plazo no activa el presupuesto de un caso.
    return problemas if len(relato) >= 450 and len(problemas) >= 4 else []


def hechos_literales(relato: str) -> list[str]:
    segmentos = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿])|\n+", relato)
    hechos = []
    for segmento in segmentos:
        segmento = segmento.strip()
        plano = normalizar(segmento)
        if not segmento or segmento.startswith("¿") or re.match(
                r"(?:quiero saber|quisiera saber|indicame|explicame|necesito saber|que obligaciones)", plano):
            continue
        hechos.append(segmento)
    return list(dict.fromkeys(hechos))[:24]


def datos_estructurados(relato: str) -> dict:
    """Conserva valores expresos con su frase de origen; nunca calcula un saldo."""
    datos = {}
    for frase in hechos_literales(relato):
        plano = normalizar(frase)
        for match in re.finditer(r"\bBs\.?\s*([\d.]+(?:,\d+)?)", frase, re.I):
            bruto = match.group(1)
            valor = Decimal(bruto.replace('.', '').replace(',', '.'))
            cercano = normalizar(frase[max(0, match.start()-45):match.end()+45])
            if re.search(r"saldo|restante|pendiente", cercano):
                clave = "saldo_pendiente"
            elif re.search(r"anticipo", cercano):
                clave = "anticipo"
            elif re.search(r"otra empresa|terminar y reparar|gasto adicional|reparacion", plano):
                clave = "gasto_adicional"
            elif re.search(r"contrat|precio|valor total", plano):
                clave = "precio_total"
            else:
                continue
            datos[clave] = {"valor": str(valor), "evidencia": frase}
    for frase in hechos_literales(relato):
        for match in re.finditer(r"(\d+(?:[.,]\d+)?)\s*%", frase):
            valor = str(Decimal(match.group(1).replace(',', '.')))
            cercano = normalizar(frase[max(0, match.start()-35):match.end()+45])
            clave = "tope_contractual" if re.search(r"maximo|tope", cercano) else "penalidad_diaria"
            datos[clave] = {"valor": valor, "evidencia": frase}
    if "precio_total" in datos and "tope_contractual" in datos:
        precio = Decimal(datos["precio_total"]["valor"])
        tope = Decimal(datos["tope_contractual"]["valor"])
        datos["calculo_tope"] = {"valor": str((precio*tope/100).quantize(Decimal('0.01'))),
            "operacion": "precio_total × tope_contractual / 100"}
    for frase in hechos_literales(relato):
        for match in re.finditer(r"\b\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)(?:\s+de\s+\d{4})?\b", frase, re.I):
            contexto = normalizar(frase[max(0, match.start()-55):match.end()+75])
            if re.search(r"comunicacion escrita|requerimiento|intimacion", contexto):
                clave = "fecha_requerimiento"
            elif re.search(r"abandon", contexto):
                clave = "fecha_abandono"
            elif re.search(r"debia entregar|entrega.*hasta", contexto):
                clave = "fecha_entrega_pactada"
            elif re.search(r"contrate|contrato.*por", contexto):
                clave = "fecha_contrato"
            else:
                clave = None
            if clave and clave not in datos:
                datos[clave] = {"valor": match.group(), "evidencia": frase}
    for frase in hechos_literales(relato):
        if re.search(r"d[ií]as adicionales", frase, re.I):
            match = re.search(r"\b(?:\d+|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+d[ií]as adicionales\b", frase, re.I)
            if match:
                datos["plazo_adicional"] = {"valor": match.group(), "evidencia": frase}
    return datos


# IDs estables por papel jurídico, no por orden de aparición en la prosa. Un ID ausente
# se omite: nunca se reutiliza para otro valor o tipo.
TIPOS_HECHO = (
    ("H1", "precio_total", "precio_total", "BOB"),
    ("H2", "anticipo", "anticipo", "BOB"),
    ("H3", "saldo_pendiente", "saldo_pendiente", "BOB"),
    ("H4", "gasto_adicional", "gasto_adicional", "BOB"),
    ("H5", "penalidad_diaria", "porcentaje_penalidad", "%"),
    ("H6", "tope_contractual", "limite_penalidad", "%"),
    ("H7", "fecha_entrega_pactada", "fecha_vencimiento", "fecha"),
    ("H8", "fecha_requerimiento", "fecha_requerimiento", "fecha"),
    ("H9", "plazo_adicional", "plazo_adicional", "días"),
    ("H10", "fecha_abandono", "fecha_abandono", "fecha"),
)
MESES = {nombre: indice for indice, nombre in enumerate((
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "octubre", "noviembre", "diciembre"), 1)}
NUMEROS_ESCRITOS = {nombre: indice for indice, nombre in enumerate((
    "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez"), 1)}


def hechos_estructurados(relato: str) -> dict[str, dict]:
    """Valores con papel y evidencia originales; el modelo solo recibe estos IDs."""
    datos = datos_estructurados(relato)
    anios = {int(v) for v in re.findall(r"\b(?:19|20)\d{2}\b", relato)}
    hechos = {}
    for identificador, clave, tipo, unidad in TIPOS_HECHO:
        if clave not in datos:
            continue
        valor = datos[clave]["valor"]
        if unidad == "fecha":
            m = re.fullmatch(r"(\d{1,2}) de (\w+)(?: de (\d{4}))?", normalizar(valor))
            if not m or m.group(2) not in MESES:
                continue
            anio = int(m.group(3)) if m.group(3) else next(iter(anios)) if len(anios) == 1 else None
            if anio is None:
                continue
            try:
                valor = date(anio, MESES[m.group(2)], int(m.group(1))).isoformat()
            except ValueError:
                continue
        elif unidad == "días":
            m = re.search(r"\b(\d+|" + '|'.join(NUMEROS_ESCRITOS) + r")\s+d[ií]as\b", normalizar(valor))
            if not m:
                continue
            valor = str(int(m.group(1)) if m.group(1).isdigit() else NUMEROS_ESCRITOS[m.group(1)])
        hechos[identificador] = {"id": identificador, "tipo": tipo, "valor": valor,
                                 "unidad": unidad, "evidencia": datos[clave]["evidencia"]}
    return MappingProxyType({clave: MappingProxyType(valor) for clave, valor in hechos.items()})


def derivaciones_verificadas(hechos: dict[str, dict]) -> dict[str, dict]:
    """Solo operaciones permitidas con operandos y resultado reproducibles."""
    if ("H1" not in hechos or "H6" not in hechos or
            hechos["H1"]["tipo"] != "precio_total" or
            hechos["H6"]["tipo"] != "limite_penalidad"):
        return MappingProxyType({})
    base = Decimal(hechos["H1"]["valor"])
    porcentaje = Decimal(hechos["H6"]["valor"])
    if base <= 0 or porcentaje <= 0 or porcentaje > 100:
        return MappingProxyType({})
    return MappingProxyType({"D1": MappingProxyType({
        "id": "D1", "tipo": "tope_calculado", "operacion": "porcentaje",
        "base_fact_id": "H1", "porcentaje_fact_id": "H6",
        "resultado": str((base * porcentaje / 100).quantize(Decimal("0.01"))),
        "unidad": "BOB"})})
