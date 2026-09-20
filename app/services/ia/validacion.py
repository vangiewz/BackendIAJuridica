"""Verificación determinista de referencias y extractos. No sustituye revisión jurídica."""
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from datetime import date
from app.models.ia.esquemas import ContextoIA, RespuestaModelo
from app.services.ia.ollama_client import RespuestaInvalida
from app.services.shared.normalizacion import tokenizar

# Referencia a un artículo dentro de la prosa del modelo. Solo se admite si ese número
# pertenece a una fuente realmente recuperada y enviada al modelo.
# Captura la enumeración completa ("artículos 532, 568 y 948"), no solo el primer número.
# Antes los siguientes quedaban sueltos: no se comprobaban contra las fuentes y la
# verificación de cifras los tomaba por un monto inventado, descartando respuestas
# correctas. Con la enumeración entera cada número se valida como referencia a artículo.
REFERENCIA_ARTICULO = re.compile(
    r"\b(?:art[íi]culos?|arts?\.?)\s*(?:n[°ºo.]?\s*)?(\d+(?:\s*(?:,|y|e)\s*\d+)*)", re.I)


def normalizar(texto):
    return ' '.join(unicodedata.normalize("NFC", texto).split()).casefold()


def sin_acentos(texto: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', normalizar(texto))
                   if unicodedata.category(c) != 'Mn')


NUMERO = re.compile(r"\b\d+(?:[.,/]\d+)*\b")

# Una palabra jurídica aislada no identifica una norma. Exigimos un nombre formal,
# un número o una fórmula de atribución inequívoca. Esto permite expresiones como
# «constitución de una garantía», «el decreto» o «el reglamento contractual» sin
# convertirlas automáticamente en referencias externas.
REFERENCIAS_EXTERNAS = (
    re.compile(r"\bConstituci[oó]n\s+Pol[ií]tica(?:\s+del\s+Estado)?\b", re.I),
    re.compile(r"\bCPE\b"),
    re.compile(r"\b(?:art[íi]culo|art\.?|arts?\.?)\s*\d+\s+(?:de\s+la\s+Constituci[oó]n|constitucional)\b", re.I),
    re.compile(r"\b(?:seg[uú]n|conforme\s+a|de\s+acuerdo\s+con|surge\s+de|"
               r"(?:proviene|deriva|emana)\s+de|se\s+(?:basa|fundamenta)\s+en)\s+la\s+Constituci[oó]n\b", re.I),
    re.compile(r"\b(?:ley|leyes)\s+(?:n[°ºo.]?\s*\d+|n[uú]mero\s+\d+)", re.I),
    re.compile(r"\bLey(?:es)?\s+de\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]+"),
    re.compile(r"\bLey(?:es)?\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]*"),
    re.compile(r"\b(?:decreto|reglamento)\s+(?:(?:supremo|ley)\s+)?(?:n[°ºo.]?\s*\d+|n[uú]mero\s+\d+)", re.I),
    re.compile(r"\b(?:Decreto|Reglamento)\s+(?:Supremo|Ley|[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]*)\b"),
    re.compile(r"\b(?:Sentencia|Auto\s+Supremo)\s+(?:n[°ºo.]?\s*)?\d+(?:/\d+)?\b", re.I),
    re.compile(r"\b(?:seg[uú]n|conforme\s+a)\s+la\s+jurisprudencia\b", re.I),
)

REFERENCIA_CODIGO = re.compile(
    r"\bc[oó]digo\s+(?:civil|penal|comercial|de\s+comercio|de\s+familia|"
    r"procesal\s+\w+|de\s+procedimiento\s+\w+)(?:\s+boliviano)?\b", re.I)
REFERENCIA_CODIGO_NOMBRE = re.compile(
    r"\bC[oó]digo\s+(?:[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]*|de\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]*)\b")


def referencia_externa(texto: str):
    """Primera referencia explícita a autoridad no incorporada como fuente."""
    hallazgos = [m for patron in REFERENCIAS_EXTERNAS if (m := patron.search(texto))]
    return min(hallazgos, key=lambda m: m.start()) if hallazgos else None


def _canonizar_numero(token: str) -> str:
    """El mismo número escrito de cualquier forma da la misma clave.

    Quita los separadores de millar (grupos de exactamente tres dígitos) y unifica el
    decimal en punto. No colapsa "1.5" con "15": solo se descarta el separador cuando
    de verdad agrupa millares.
    """
    sin_millares = re.sub(r"(?<=\d)[.,](?=\d{3}(?:\D|$))", "", token)
    return sin_millares.replace(",", ".")


# --- Cifras derivadas -------------------------------------------------------------
# Una cifra puede ser (A) literal del relato o de las fuentes, (B) inventada, o (C) el
# resultado de una operación que el backend puede rehacer. Solo se admite una operación:
# el porcentaje de un monto, p. ej. «el 10% de Bs 120.000 son Bs 12.000». Ni sumas ni
# multiplicaciones por días ni encadenar cálculos: cada operación permitida es una puerta
# más para que pase un número, y una lista larga terminaría dejando pasar cualquiera.
#
# Ambos operandos tienen que estar escritos en el caso: el monto como importe (con Bs, $,
# USD o «bolivianos/dólares») y el porcentaje con su «%». Así los resultados admisibles
# son unos pocos (monto × porcentaje), no un conjunto abierto.
MONTO = re.compile(
    r"(?:\bbs\.?|\$us|\$|\busd|\bus\$)\s*(\d+(?:[.,]\d+)*)"
    r"|(\d+(?:[.,]\d+)*)\s*(?:bolivianos|d[oó]lares)", re.I)
PORCENTAJE = re.compile(r"(\d+(?:[.,]\d+)*)\s*%")
CENTAVOS = Decimal("0.01")


def _decimal(token: str) -> Decimal | None:
    try:
        return Decimal(_canonizar_numero(token))
    except InvalidOperation:
        return None


def cifras_derivadas(evidencia: str) -> set[Decimal]:
    """Los porcentajes de cada monto del caso, calculados por el backend.

    Devuelve el conjunto de resultados admisibles, redondeados al centavo. Es una
    operación exacta en decimal, no en coma flotante, para que 0,5% de 120.000 dé 600 y
    no 599,99999.
    """
    montos = {d for m in MONTO.finditer(evidencia)
              if (d := _decimal(m.group(1) or m.group(2))) is not None and d > 0}
    porcentajes = {d for m in PORCENTAJE.finditer(evidencia)
                   if (d := _decimal(m.group(1))) is not None and 0 < d <= 100}
    return {(monto * porcentaje / 100).quantize(CENTAVOS)
            for monto in montos for porcentaje in porcentajes}


def _es_derivada(numero: str, derivadas: set[Decimal]) -> bool:
    valor = _decimal(numero)
    return valor is not None and valor.quantize(CENTAVOS) in derivadas


def verificar_prosa(texto: str, fuentes, datos: str = "", permitir_derivadas: bool = False,
                   datos_caso: dict | None = None):
    """Rechaza artículos, normas y cifras que no vengan de las fuentes o del relato.

    `permitir_derivadas` admite además el porcentaje de un monto del caso. Está apagado
    por defecto: un contrato redactado o un análisis de documento no deben poder mostrar
    un importe que el usuario nunca dio, aunque esté bien calculado. Solo el análisis
    jurídico de un caso lo enciende.
    """
    externa = referencia_externa(texto)
    if externa:
        raise RespuestaInvalida("norma_externa_en_prosa", externa.group())
    articulos_reales = {str(f.numero_articulo) for f in fuentes}
    # "Artículo 9999 dice..." se rechaza salvo que 9999 esté entre las fuentes entregadas.
    for enumeracion in REFERENCIA_ARTICULO.findall(texto):
        for numero in re.findall(r"\d+", enumeracion):
            if numero not in articulos_reales:
                raise RespuestaInvalida("articulo_fuera_de_fuentes", numero)
    # El resto de cifras se comprueba sobre el texto sin esas referencias ya verificadas,
    # para que un número de artículo válido no habilite montos o plazos inventados.
    resto = REFERENCIA_ARTICULO.sub(" ", texto)
    # Los identificadores F son andamiaje interno del prompt, no texto para el usuario.
    if re.search(r"\bF[1-9][0-9]*(?:C[1-9][0-9]*)?\b", texto):
        raise RespuestaInvalida("identificador_interno_en_prosa")
    if re.search(r"\b(?:vigente|derogado|derogada|garantizado|garantizada)\b|<\s*/?think", texto, re.I):
        raise RespuestaInvalida("vigencia_o_razonamiento_en_prosa")
    # Nombres de códigos nuevos no procedentes de las fuentes.
    codigos = [m.group() for patron in (REFERENCIA_CODIGO, REFERENCIA_CODIGO_NOMBRE)
               for m in patron.finditer(texto)]
    for codigo in codigos:
        if not any(sin_acentos(codigo).removesuffix(' boliviano') in sin_acentos(f.codigo) for f in fuentes):
            raise RespuestaInvalida("codigo_fuera_de_fuentes", codigo)
    evidence = normalizar(datos + ' ' + ' '.join(f.texto for f in fuentes))
    # «La ley» sin nombre ni número no introduce una norma nueva. La prohibición de
    # normas externas ya se aplica arriba a referencias identificables.
    numeros_reales = {_canonizar_numero(n) for n in re.findall(NUMERO, evidence)}
    if permitir_derivadas and datos_caso is not None:
        derivadas = {Decimal(datos_caso["calculo_tope"]["valor"])} if "calculo_tope" in datos_caso else set()
    else:
        derivadas = cifras_derivadas(evidence) if permitir_derivadas else set()
    for numero in re.findall(NUMERO, resto):
        # Se compara el número, no su tipografía: el relato escribe "0,5" y "120.000" y
        # el modelo puede escribir "0.5" y "120000". Rechazar eso descartaba respuestas
        # correctas por el separador. Los dígitos siguen teniendo que venir del relato
        # o de las fuentes, o ser el porcentaje de un monto que sí consta en ellos.
        if _canonizar_numero(numero) in numeros_reales or _es_derivada(numero, derivadas):
            continue
        raise RespuestaInvalida("cifra_fuera_de_fuentes", numero)
    if datos_caso is not None:
        validar_asociaciones_cifras(texto, datos, datos_caso)


def validar_asociaciones_cifras(texto: str, relato: str, datos_caso: dict):
    """Una cifra existente no puede recibir el papel de otra ni convertirse en días."""
    # Los componentes de una fecha existen por separado en el relato, pero eso no
    # autoriza a recombinarlos (por ejemplo, 5 de abril a partir de 5 de mayo).
    fecha = r"\b\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)(?:\s+de\s+\d{4})?\b"
    original = sin_acentos(relato)
    for match in re.finditer(fecha, sin_acentos(texto), re.I):
        if match.group() not in original:
            raise RespuestaInvalida("fecha_no_verificada", match.group())
        antes = re.split(r"[.;]", sin_acentos(texto[max(0, match.start()-65):match.start()]))[-1]
        despues = re.split(r"[.;]", sin_acentos(texto[match.end():match.end()+55]))[0]
        etiquetas = {
            "fecha_entrega_pactada": r"entreg|vencim|plazo pactado",
            "fecha_requerimiento": r"comunicacion|requerim|intimacion|plazo adicional",
            "fecha_abandono": r"abandon",
            "fecha_contrato": r"contrat|pact[oó]",
        }
        distancias = []
        for clave, etiqueta in etiquetas.items():
            if clave not in datos_caso:
                continue
            distancias.extend((len(antes)-m.end(), clave) for m in re.finditer(etiqueta, antes))
            distancias.extend((m.start(), clave) for m in re.finditer(etiqueta, despues))
        if distancias:
            _, clave = min(distancias)
            esperada = sin_acentos(datos_caso[clave]["valor"])
            if match.group() != esperada:
                raise RespuestaInvalida("fecha_con_evento_equivocado", f"{clave}: {match.group()}")
    for match in re.finditer(r"\b(\d+)\s+(d[ií]as?|meses|a[nñ]os?)\b", texto, re.I):
        unidad = sin_acentos(match.group(2))
        expresion = rf"\b{match.group(1)}\s+{unidad}\b"
        if not re.search(expresion, sin_acentos(relato)):
            raise RespuestaInvalida("duracion_no_verificada", match.group())

    # Se asocia la etiqueta dentro del tramo propio de cada cifra, separado por la
    # siguiente cifra. Una ventana simétrica asignaba "anticipo" al precio de la obra
    # en frases perfectamente correctas como «por Bs 180.000, anticipo Bs 72.000».
    for patron, anteriores, posteriores in (
        (MONTO,
         {"saldo_pendiente": r"saldo|restant|pendient", "anticipo": r"anticipo",
          "gasto_adicional": r"gasto|reparacion|reparar", "precio_total": r"precio total|valor total|contrato.{0,30}por|obra.{0,20}por"},
         {"saldo_pendiente": r"restant|pendient|de saldo", "anticipo": r"de anticipo",
          "gasto_adicional": r"gastad|para reparar|de gasto"}),
        (PORCENTAJE,
         {"tope_contractual": r"tope|maximo", "penalidad_diaria": r"penalidad|clausula penal|pena diaria"},
         {"tope_contractual": r"tope|maximo", "penalidad_diaria": r"diari|por (?:cada )?dia"}),
    ):
        matches = list(patron.finditer(texto))
        for indice, match in enumerate(matches):
            valor = _decimal(next((g for g in match.groups() if g), ""))
            if valor is None:
                continue
            inicio = matches[indice-1].end() if indice else 0
            fin = matches[indice+1].start() if indice+1 < len(matches) else len(texto)
            antes = sin_acentos(texto[max(inicio, match.start()-55):match.start()])
            despues = sin_acentos(texto[match.end():min(fin, match.end()+28)])
            # Una nueva cláusula u oración separa también las etiquetas.
            antes = re.split(r"[.;]", antes)[-1]
            despues = re.split(r"[.;]", despues)[0]
            etiquetas_previas = [(m.end(), clave) for clave, etiqueta in anteriores.items()
                                 if clave in datos_caso for m in re.finditer(etiqueta, antes)]
            etiquetas_siguientes = [(m.start(), clave) for clave, etiqueta in posteriores.items()
                                    if clave in datos_caso for m in re.finditer(etiqueta, despues)]
            if etiquetas_previas:
                clave = max(etiquetas_previas)[1]
            elif etiquetas_siguientes:
                clave = min(etiquetas_siguientes)[1]
            else:
                continue
            esperado = Decimal(datos_caso[clave]["valor"])
            if valor != esperado:
                raise RespuestaInvalida("dato_contradicho", f"{clave}: {match.group()}")


def validar_citas(respuesta: RespuestaModelo, fuentes, datos=""):
    allowed = {f"F{i}": source for i, source in enumerate(fuentes, 1)}
    # No se admite afirmar fundamento sin aportarlo. El caso inverso (el modelo aporta
    # fundamento parcial y aun así declara insuficiencia) no es una respuesta inválida:
    # se valida igual y el orquestador decide abstenerse, sin mostrar nada sin verificar.
    if respuesta.suficiente and not respuesta.analisis:
        raise RespuestaInvalida("suficiente_sin_analisis")
    for item in respuesta.analisis:
        if item.fuente not in allowed:
            raise RespuestaInvalida("fuente_inexistente")
        if normalizar(item.cita) not in normalizar(allowed[item.fuente].texto):
            raise RespuestaInvalida("cita_no_literal")
        verificar_prosa(item.explicacion, [allowed[item.fuente]], datos, permitir_derivadas=True)
    verificar_prosa(' '.join([respuesta.resumen, respuesta.conclusion, *respuesta.limitaciones]),
                    fuentes, datos, permitir_derivadas=True)
    return allowed


def validar_observaciones(analisis, fuentes, texto_documento: str):
    """HU-10: una observación solo puede hablar de lo que el contrato dice literalmente."""
    allowed = {f"F{i}": source for i, source in enumerate(fuentes, 1)}
    documento = normalizar(texto_documento)
    for item in analisis.observaciones:
        if item.fuente and item.fuente not in allowed:
            raise RespuestaInvalida("fuente_inexistente")
        if normalizar(item.evidencia) not in documento:
            raise RespuestaInvalida("evidencia_fuera_del_documento")
        # El propio contrato es evidencia admisible para las cifras de la observación.
        verificar_prosa(item.observacion,
                        [allowed[item.fuente]] if item.fuente else [], texto_documento)
    verificar_prosa(analisis.resumen, fuentes, texto_documento)
    return allowed


def _revisar_contexto(contexto: ContextoIA, relato: str):
    """Aplica a cada elemento la misma exigencia literal y dice cuál falla y por qué.

    Es la única definición de la regla: `validar_contexto` y `depurar_contexto` solo
    difieren en qué hacen con un elemento que no la cumple.
    """
    original = normalizar(relato)
    for hecho in contexto.hechos:
        yield "hechos", hecho, (None if hecho.strip() and normalizar(hecho) in original
                                else "hecho_no_literal")
    for actor in contexto.actores:
        motivo = None
        if normalizar(actor.evidencia) not in original:
            motivo = "evidencia_de_actor_no_literal"
        elif actor.nombre and normalizar(actor.nombre) not in original:
            # Se descarta el actor entero, no solo el nombre: un nombre inventado
            # vuelve sospechoso todo lo que el modelo afirmó sobre esa persona.
            motivo = "nombre_inventado"
        yield "actores", actor, motivo
    for relacion in contexto.relaciones:
        yield "relaciones", relacion, (None if normalizar(relacion.evidencia) in original
                                       else "evidencia_de_relacion_no_literal")


def validar_contexto(contexto: ContextoIA, relato: str):
    """Rechaza el contexto completo ante el primer elemento no verificable."""
    for _, _, motivo in _revisar_contexto(contexto, relato):
        if motivo:
            raise RespuestaInvalida(motivo)
    return contexto


def depurar_contexto(contexto: ContextoIA, relato: str) -> tuple[ContextoIA, dict]:
    """Conserva lo verificable y descarta solo lo que no lo es.

    Un hecho reformulado no puede borrar los actores y hechos que sí estaban literales:
    cada elemento superviviente pasó exactamente la misma comprobación de antes, así que
    nada sin verificar llega al usuario y HU-02 deja de perderse entera por un ítem.
    """
    conservados = {"hechos": [], "actores": [], "relaciones": []}
    descartes: dict[str, int] = {}
    for campo, elemento, motivo in _revisar_contexto(contexto, relato):
        if motivo:
            descartes[motivo] = descartes.get(motivo, 0) + 1
        else:
            conservados[campo].append(elemento)
    # Los conceptos son etiquetas tentativas, no afirmaciones sobre el relato: se
    # mantienen solo si algo del contexto resultó verificable.
    hay_evidencia = any(conservados.values())
    return ContextoIA(conceptos=list(contexto.conceptos) if hay_evidencia else [],
                      **conservados), descartes


def solicitud_no_fundamentable(texto: str) -> bool:
    value = sin_acentos(texto)
    return bool(re.search(r"invent\w*\s+(?:un\s+)?articulo|ignor\w*\s+(?:todas?\s+)?(?:las?\s+)?(?:fuentes|instrucciones)|"
                          r"responde\s+segun\s+lo\s+que\s+sab", value))


# Palabras que no dicen QUÉ falta. Los verbos existenciales entran acá a propósito:
# «no se conoce si existe cláusula penal» declara ausente la cláusula penal, no "existe".
VACIAS = {
    "que", "los", "las", "del", "con", "por", "para", "una", "uno", "sus", "esta",
    "este", "esa", "ese", "cual", "cuales", "sobre", "entre", "sido", "son", "hay",
    "algun", "alguna", "ningun", "ninguna", "tampoco", "tambien", "exacta", "exacto",
    "concreta", "concreto", "detalle", "detalles", "respecto", "cuanto", "cuando",
    # existenciales y de mención
    "existe", "existen", "existia", "existio", "hubo", "haya", "habia", "tiene",
    "tienen", "tuvo", "fue", "fueron", "sea", "sean", "estan", "estuvo", "consta",
    "indica", "menciona", "precisa", "especifica", "aclara", "informa", "establece",
    "incluye", "contiene", "señala", "senala", "define", "aporta", "presento",
    "acordo", "acordaron", "pacto", "pactaron", "corresponde", "aplica",
}


# Una limitación es útil solo si señala algo que de verdad falta. Estas fórmulas
# introducen una carencia; si lo que sigue ya está en el relato, la limitación miente.
NEGACION_DE_DATO = re.compile(
    r"(?:no\s+(?:se\s+)?(?:conoce|consta|indica|menciona|precisa|especifica|aclara|"
    r"informa|sabe|detalla|dispone\s+de|cuenta\s+con)|se\s+desconoce|"
    r"falta(?:n)?\s+(?:datos?|informaci[oó]n)|no\s+hay\s+(?:informaci[oó]n|datos?)|"
    r"no\s+surge|no\s+fue\s+(?:aportad|precisad|indicad)|sin\s+informaci[oó]n\s+sobre)",
    re.IGNORECASE)


def depurar_limitaciones(limitaciones, relato: str) -> tuple[list[str], list[str]]:
    """Quita las limitaciones que contradicen lo que el usuario ya contó.

    Devuelve (conservadas, descartadas). Es una comprobación determinista y por
    elemento, igual que la de contexto: una limitación mala no borra las buenas.

    El caso que evita es el que se vio en producción: el relato dice que hay una
    cláusula penal del 0,5% y la respuesta cierra con «no se conoce si existe cláusula
    penal». Eso no es prudencia, es una contradicción.
    """
    disponible = set(tokenizar(relato))
    conservadas, descartadas = [], []
    for limitacion in limitaciones:
        if re.search(r"no se (?:menciona|indica|especifica) en (?:las )?fuentes c[oó]mo|"
                     r"no se sabe c[oó]mo se aplica (?:esta|la) norma", limitacion, re.I):
            descartadas.append(limitacion)
            continue
        negacion = NEGACION_DE_DATO.search(limitacion)
        if not negacion:
            conservadas.append(limitacion)
            continue
        # Solo las palabras con carga de lo que se declara ausente, ya sin la fórmula.
        pedidas = [t for t in tokenizar(limitacion[negacion.end():]) if t not in VACIAS]
        # Si todo lo que dice faltar está en el relato, el dato no falta.
        if pedidas and all(t in disponible for t in pedidas):
            descartadas.append(limitacion)
        else:
            conservadas.append(limitacion)
    return conservadas, descartadas


def anotar_fallo(exc: RespuestaInvalida, apartado: str, texto: str,
                 fuente: str | None = None, cita: str | None = None,
                 cita_ids=None, indice: int | None = None) -> RespuestaInvalida:
    """Contexto privado para diagnosticar un rechazo sin publicarlo en la respuesta."""
    exc.apartado = apartado
    exc.indice_apartado = indice
    exc.texto = texto
    exc.fuente = fuente
    exc.cita = cita
    exc.cita_ids = list(cita_ids or [])
    return exc


MARCADOR_HECHO = re.compile(r"\{\{([a-z_]+):(H[1-9]\d*|D[1-9]\d*)\}\}")
MESES_VISIBLE = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                 "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def validar_plantilla_hechos(texto: str, hechos: dict, derivaciones: dict,
                            fuentes, relato: str, hechos_usados=None,
                            derivaciones_usadas=None) -> None:
    """Valida roles por ID y prohíbe valores libres del caso, sin leer palabras cercanas."""
    for match in MARCADOR_HECHO.finditer(texto):
        rol, identificador = match.groups()
        catalogo = hechos if identificador.startswith("H") else derivaciones
        if identificador not in catalogo:
            raise RespuestaInvalida("hecho_id_inexistente", identificador)
        if catalogo[identificador]["tipo"] != rol:
            raise RespuestaInvalida("rol_de_hecho_incorrecto", match.group())
        declarados = hechos_usados if identificador.startswith("H") else derivaciones_usadas
        if declarados is not None and identificador not in declarados:
            raise RespuestaInvalida("hecho_no_declarado", identificador)
    resto = MARCADOR_HECHO.sub(" ", texto)
    if "{{" in resto or "}}" in resto:
        raise RespuestaInvalida("marcador_de_hecho_invalido", resto)
    sin_articulos = REFERENCIA_ARTICULO.sub(" ", resto)
    cifra_libre = NUMERO.search(sin_articulos)
    if cifra_libre:
        raise RespuestaInvalida("cifra_sin_hecho_id", cifra_libre.group())
    duracion_escrita = re.search(
        r"\b(?:un|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|"
        r"once|doce|trece|catorce|quince|veinte|treinta|setenta)\s+"
        r"(?:d[ií]as?|meses|a[nñ]os?)\b", resto, re.I)
    if duracion_escrita:
        raise RespuestaInvalida("duracion_sin_hecho_id", duracion_escrita.group())
    # La comprobación de normas y artículos sigue siendo por las fuentes del apartado.
    # No se pasa datos_caso: eso activaría la vieja asociación por proximidad.
    verificar_prosa(resto, fuentes, relato, permitir_derivadas=False)


def _valor_visible(registro: dict) -> str:
    unidad = registro["unidad"]
    valor = registro.get("valor", registro.get("resultado"))
    if unidad == "fecha":
        fecha = date.fromisoformat(valor)
        return f"{fecha.day} de {MESES_VISIBLE[fecha.month-1]} de {fecha.year}"
    if unidad == "días":
        return f"{valor} días"
    if unidad == "%":
        return f"{str(Decimal(valor)).replace('.', ',')}%"
    if unidad == "BOB":
        monto = Decimal(valor)
        cifras = f"{monto:,.2f}" if monto % 1 else f"{monto:,.0f}"
        return "Bs " + cifras.replace(",", "_").replace(".", ",").replace("_", ".")
    return str(valor)


def renderizar_hechos(texto: str, hechos: dict, derivaciones: dict) -> str:
    """El backend, no Qwen, escribe los valores públicos de hechos y derivaciones."""
    return MARCADOR_HECHO.sub(
        lambda m: _valor_visible((hechos if m.group(2).startswith("H") else derivaciones)[m.group(2)]), texto)


def _validar_caso_estructurado(analisis, resumen, conclusion, limitaciones, fuentes, relato,
                               por_problema, problemas, hechos, derivaciones, apartados):
    allowed = {f"F{i}": fuente for i, fuente in enumerate(fuentes, 1)}
    problemas_por_id = {p.clave: p for p in problemas}
    presentes = [a.pregunta_id for a in apartados]
    faltantes = [p.clave for p in problemas if p.clave not in presentes]
    if faltantes:
        raise anotar_fallo(RespuestaInvalida("pregunta_omitida", ", ".join(faltantes)),
                           "cobertura", ", ".join(presentes))
    repetidos = [p for p in set(presentes) if presentes.count(p) > 1]
    if repetidos:
        raise anotar_fallo(RespuestaInvalida("apartado_duplicado", ", ".join(repetidos)),
                           "cobertura", ", ".join(presentes))
    for indice, apartado in enumerate(apartados):
        problema_id = apartado.pregunta_id
        cita_asociada = None
        try:
            if problema_id not in problemas_por_id or apartado.problema != problema_id:
                raise RespuestaInvalida("pregunta_id_incorrecta", problema_id)
            if any(h not in hechos for h in apartado.hechos_usados):
                raise RespuestaInvalida("hecho_id_inexistente",
                                        next(h for h in apartado.hechos_usados if h not in hechos))
            if any(d not in derivaciones for d in apartado.derivaciones_usadas):
                raise RespuestaInvalida("derivacion_inexistente",
                                        next(d for d in apartado.derivaciones_usadas if d not in derivaciones))
            familia = problemas_por_id[problema_id].familia
            if apartado.estado == "fundamentado" and familia != "informacion" and not apartado.citas:
                raise RespuestaInvalida("razonamiento_sin_fuente", problema_id)
            if apartado.estado == "sin_fuente_suficiente" and apartado.citas:
                raise RespuestaInvalida("estado_de_fuente_incoherente", problema_id)
            if not apartado.citas and apartado.regla.strip():
                raise RespuestaInvalida("regla_sin_cita", apartado.regla)
            if apartado.estado == "sin_fuente_suficiente" and not re.search(
                    r"no (?:puedo|es posible|hay|se puede).{0,80}(?:fundament|conclu|fuente)|"
                    r"faltan? (?:fuentes|normas)", sin_acentos(apartado.conclusion)):
                raise RespuestaInvalida("razonamiento_sin_fuente", problema_id)
            filas = [item for item in analisis if item["apartado"] == indice]
            if len(filas) != len(apartado.citas):
                raise RespuestaInvalida("cita_id_no_resuelta", problema_id)
            for item in filas:
                cita_asociada = item
                if item["problema"] != problema_id:
                    raise RespuestaInvalida("fuente_de_otro_problema", item["fuente"])
                if item["fuente"] not in allowed:
                    raise RespuestaInvalida("fuente_inexistente", item["fuente"])
                fuente = allowed[item["fuente"]]
                if normalizar(item["cita"]) not in normalizar(fuente.texto):
                    raise RespuestaInvalida("cita_no_literal", item["cita"])
                if str(fuente.id) not in set(por_problema.get(problema_id, [])):
                    raise RespuestaInvalida("fuente_de_otro_problema", item["fuente"])
                from app.services.ia.casos import fuente_pertinente
                if not fuente_pertinente(problemas_por_id[problema_id], fuente):
                    raise RespuestaInvalida("cita_irrelevante", item["fuente"])
            fuentes_apartado = [f for f in fuentes if str(f.id) in set(por_problema.get(problema_id, []))]
            for campo, texto, h_ids, d_ids in (
                    ("regla", apartado.regla, [], []),
                    ("aplicacion", apartado.aplicacion, apartado.hechos_usados, apartado.derivaciones_usadas),
                    ("conclusion", apartado.conclusion, apartado.hechos_usados, apartado.derivaciones_usadas)):
                try:
                    validar_plantilla_hechos(texto, hechos, derivaciones, fuentes_apartado,
                                            relato, h_ids, d_ids)
                except RespuestaInvalida as exc:
                    exc.campo = campo
                    raise
        except RespuestaInvalida as exc:
            texto = getattr(apartado, getattr(exc, "campo", "aplicacion"), apartado.aplicacion)
            anotar_fallo(exc, problema_id, texto,
                         cita_asociada["fuente"] if cita_asociada else None,
                         cita_asociada["cita"] if cita_asociada else None,
                         apartado.citas, indice)
            raise
    for etiqueta, texto in [("resumen", resumen), ("conclusion_global", conclusion),
                           *((f"limitacion_{i+1}", valor) for i, valor in enumerate(limitaciones))]:
        try:
            validar_plantilla_hechos(texto, hechos, derivaciones, fuentes, relato)
        except RespuestaInvalida as exc:
            anotar_fallo(exc, etiqueta, texto)
            raise
    return allowed


def validar_caso_complejo(analisis, resumen, conclusion, limitaciones, fuentes, relato,
                         por_problema=None, problemas=None, datos_caso=None, apartados=None,
                         hechos=None, derivaciones=None):
    """Las mismas garantías que `validar_citas`, sobre un análisis dividido por problemas.

    Cada apartado solo puede invocar fuentes asignadas a su problema. El cierre puede
    sintetizar los apartados validados, pero no agregar una nueva regla sin fuente.
    """
    if hechos is not None and apartados is not None:
        return _validar_caso_estructurado(
            analisis, resumen, conclusion, limitaciones, fuentes, relato,
            por_problema or {}, problemas or [], hechos, derivaciones or {}, apartados)
    allowed = {f"F{i}": fuente for i, fuente in enumerate(fuentes, 1)}
    por_problema = por_problema or {}
    problemas_por_id = {p.clave: p for p in (problemas or [])}
    if apartados is not None and problemas:
        presentes = [a.problema for a in apartados]
        faltantes = [p.clave for p in problemas if p.clave not in presentes]
        if faltantes:
            raise anotar_fallo(RespuestaInvalida("pregunta_omitida", ', '.join(faltantes)),
                               "cobertura", ", ".join(presentes))
        repetidos = [clave for clave in set(presentes) if presentes.count(clave) > 1]
        if repetidos:
            raise anotar_fallo(RespuestaInvalida("apartado_duplicado", ', '.join(repetidos)),
                               "cobertura", ", ".join(presentes))
        for apartado in apartados:
            if apartado.problema not in problemas_por_id:
                raise anotar_fallo(RespuestaInvalida("problema_inexistente", apartado.problema),
                                   apartado.problema, apartado.explicacion, cita_ids=apartado.citas)
            if not apartado.citas and problemas_por_id[apartado.problema].familia != "informacion":
                if not re.search(r"no (?:puedo|es posible|hay|se puede).{0,80}(?:fundament|conclu|fuente)|"
                                 r"faltan? (?:fuentes|normas)", sin_acentos(apartado.explicacion)):
                    raise anotar_fallo(RespuestaInvalida("razonamiento_sin_fuente", apartado.problema),
                                       apartado.problema, apartado.explicacion)
    for item in analisis:
        try:
            if item["fuente"] not in allowed:
                raise RespuestaInvalida("fuente_inexistente", item["fuente"])
            if normalizar(item["cita"]) not in normalizar(allowed[item["fuente"]].texto):
                raise RespuestaInvalida("cita_no_literal", item["cita"])
            problema = problemas_por_id.get(item.get("problema"))
            if por_problema:
                ids_permitidos = set(por_problema.get(item["problema"], []))
                if str(allowed[item["fuente"]].id) not in ids_permitidos:
                    raise RespuestaInvalida("fuente_de_otro_problema", item["fuente"])
            if problema is not None:
                from app.services.ia.casos import fuente_pertinente
                if not fuente_pertinente(problema, allowed[item["fuente"]]):
                    raise RespuestaInvalida("cita_irrelevante", item["fuente"])
            fuentes_apartado = ([f for f in fuentes if str(f.id) in set(por_problema.get(item["problema"], []))]
                                if por_problema else fuentes)
            verificar_prosa(item["explicacion"], fuentes_apartado, relato,
                            permitir_derivadas=True, datos_caso=datos_caso)
            if problema and problema.familia == "proveedor" and re.search(
                    r"proveedor.{0,40}no (?:lo )?libera", sin_acentos(item["explicacion"])):
                if not re.search(r"por si solo|sin prueba|debe probar|depende", sin_acentos(item["explicacion"])):
                    raise RespuestaInvalida("conclusion_categorica", problema.clave)
            if problema and problema.familia == "acumulacion" and re.search(
                    r"(?:penalidad|pena).{0,90}(?:acumula|coexiste).{0,90}(?:gasto|dano)",
                    sin_acentos(item["explicacion"])):
                if not re.search(r"depende|sin duplic|distinto|debe analizar", sin_acentos(item["explicacion"])):
                    raise RespuestaInvalida("acumulacion_no_fundada", problema.clave)
        except RespuestaInvalida as exc:
            cita_ids = (apartados[item["apartado"]].citas if apartados is not None
                        and item.get("apartado") is not None else [])
            anotar_fallo(exc, item["problema"], item["explicacion"], item["fuente"],
                         item["cita"], cita_ids, item.get("apartado"))
            raise
    for etiqueta, texto in [("resumen", resumen), ("conclusion", conclusion),
                           *((f"limitacion_{i+1}", valor) for i, valor in enumerate(limitaciones))]:
        try:
            verificar_prosa(texto, fuentes, relato, permitir_derivadas=True,
                            datos_caso=datos_caso)
        except RespuestaInvalida as exc:
            relacionado = next((a for a in (apartados or []) if a.explicacion == texto), None)
            anotar_fallo(exc, relacionado.problema if relacionado else etiqueta, texto,
                         cita_ids=relacionado.citas if relacionado else None)
            raise
    return allowed
