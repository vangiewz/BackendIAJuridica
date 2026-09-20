"""Full-text existente + coseno exacto pgvector + RRF simétrico (k=60)."""
import re
from collections import Counter
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from time import perf_counter
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.models.conocimiento.norma import Norma
from app.models.conocimiento.embedding import NormaEmbedding
from app.services.conocimiento.busqueda_lexica import buscar_candidatos, buscar_candidatos_por_conceptos
from app.services.ia.embeddings import embedding_consulta, documento_norma, huella_documento
from app.services.ia.ollama_client import OllamaClient, IAError, IANoDisponible
from app.services.conocimiento.expansion_consulta import expandir_consulta
from app.services.ia.metricas import medir
from app.services.shared.normalizacion import normalizar
from app.services.ia.casos import fuente_pertinente

RRF_K = 60  # constante del trabajo original; canales simétricos, sin pesos aprendidos


def pertinencia_suficiente(consulta: str, norma: Norma) -> bool:
    """Exige nexo entre incumplimiento y consecuencia en esta consulta amplia.

    Un articulo sobre una responsabilidad especial puede ser real y lateral.
    La regla usa conceptos, nunca numeros de articulos.
    """
    if "responsabilidad contractual" not in normalizar(consulta):
        return True
    texto = normalizar(f"{norma.epigrafe or ''} {norma.texto}")
    incumplimiento = any(s in texto for s in (
        "incumpl", "no cumple", "no cumpl", "retras", "mora"))
    consecuencia = any(s in texto for s in (
        "resarc", "dano", "perjuicio", "responsab"))
    return incumplimiento and consecuencia


def _prioridad_conceptual(norma: Norma) -> int:
    """Premia una regla general sobre incumplimiento y su consecuencia."""
    epigrafe = normalizar(norma.epigrafe or "")
    texto = normalizar(norma.texto)
    return (3 * ("responsabilidad" in epigrafe and "deudor" in epigrafe)
            + 2 * ("resarcimiento" in epigrafe and "pecuniari" not in epigrafe)
            + ("contrato" in texto)
            - ("requerimiento" in epigrafe))


def _raices(texto: str) -> set[str]:
    """Raíces de seis letras: «arrendada» y «arrendamiento» cuentan como el mismo tema."""
    return {palabra[:6] for palabra in re.findall(r"[a-z]{4,}", normalizar(texto))}


def ancla_tematica(conceptos: list[str]) -> str | None:
    """La raíz que comparten varios conceptos: la institución de la que trata la consulta.

    Cuando el relato dispara varios patrones a la vez —arrendamiento, enajenación de la
    cosa arrendada, extinción, duración— todos giran alrededor de la misma raíz. Esa
    coincidencia identifica el tema sin nombrar ninguna norma. Si un solo patrón se
    activa no hay convergencia y no se fija ancla: el orden queda como estaba.
    """
    if len(conceptos) < 2:
        return None
    cuenta = Counter(raiz for concepto in conceptos for raiz in _raices(concepto))
    raiz, veces = cuenta.most_common(1)[0]
    return raiz if veces > 1 else None


def afinidad_tematica(conceptos: list[str], norma: Norma, ancla: str | None = None) -> int:
    """Cercanía entre el tema que plantea la consulta y lo que regula la norma.

    RRF mide acuerdo entre canales, no pertinencia temática: una consulta sobre
    arrendamiento recuperaba artículos de responsabilidad y de carga de la prueba
    porque compartían palabras genéricas. Acá se compara la consulta —a través de los
    conceptos que ella misma disparó— con el epígrafe, que es donde la norma dice qué
    institución regula. Palabras sueltas como «restitución» o «plazo» aparecen en
    figuras distintas (depósito, comodato, superficie), así que pesa más que la norma
    trate del ancla que compartieron los conceptos. La regla es general y no menciona
    ningún número de artículo.
    """
    if not conceptos:
        return 0
    raices = _raices(' '.join(conceptos))
    epigrafe = _raices(norma.epigrafe or "")
    cuerpo = _raices(norma.texto)
    del_tema = 6 * int(bool(ancla) and ancla in (epigrafe | cuerpo))
    return del_tema + 2 * len(raices & epigrafe) + len(raices & cuerpo)


def fusionar_rankings(rankings: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    if k < 1:
        raise ValueError("k debe ser positivo")
    scores = {}
    for ranking in rankings:
        seen = set()
        for position, key in enumerate(ranking, 1):
            if key in seen:
                continue
            seen.add(key)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + position)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


@dataclass
class Coincidencia:
    Norma: Norma
    relevancia: float
    rango_lexico: int | None = None
    rango_semantico: int | None = None
    similitud: float | None = None


@dataclass
class Recuperacion:
    resultados: list[Coincidencia]
    modo: str
    tiempos_ms: dict[str, float] = field(default_factory=dict)
    advertencia: str | None = None
    por_problema: dict[str, list[str]] = field(default_factory=dict)


def buscar_semantica(db: Session, consulta: str, limite: int = 20,
                     area: str | None = None, client: OllamaClient | None = None) -> list[Coincidencia]:
    client = client or OllamaClient()
    vector, digest = _preparar_vector(consulta, client)
    return _buscar_vector(db, vector, digest, limite, area, client)


def _preparar_vector(consulta, client):
    digest = client.modelos().get(client.settings.embedding_model)
    if not digest:
        raise IANoDisponible()
    with medir("expansion"):
        _, conceptos = expandir_consulta(consulta)
    texto_semantico = consulta + ("\nConceptos de búsqueda: " + '; '.join(conceptos) if conceptos else "")
    with medir("embedding"):
        vector = embedding_consulta(client, texto_semantico)
    if len(vector) != 1024:
        raise IAError("El modelo de embeddings no coincide con el índice de 1024 dimensiones.")
    return vector, digest


def _buscar_vector(db, vector, digest, limite, area, client):
    distance = NormaEmbedding.vector.cosine_distance(vector).label("distancia")
    stmt = (select(Norma, NormaEmbedding.contenido_hash, distance)
            .join(NormaEmbedding, NormaEmbedding.norma_id == Norma.id)
            .where(Norma.activa.is_(True), NormaEmbedding.modelo == client.settings.embedding_model,
                   NormaEmbedding.modelo_digest == digest, NormaEmbedding.dimension == len(vector)))
    if area:
        stmt = stmt.where(Norma.area_juridica == area)
    # Para 1570 artículos, ranking exacto. Verificar hash impide usar vectores obsoletos.
    results = []
    offset = 0
    batch_size = max(40, limite*2)
    while len(results) < limite:
        with medir("vector"):
            rows = db.execute(stmt.order_by(distance, Norma.id).limit(batch_size).offset(offset)).all()
        for norma, fingerprint, dist in rows:
            if fingerprint != huella_documento(documento_norma(norma)):
                continue
            results.append(Coincidencia(norma, 1-float(dist),
                                       rango_semantico=len(results)+1, similitud=1-float(dist)))
            if len(results) == limite:
                break
        if len(rows) < batch_size:
            break
        offset += batch_size
    return results


def buscar_hibrida(db: Session, consulta: str, limite: int | None = None,
                   area: str | None = None, client: OllamaClient | None = None,
                   problemas=None) -> Recuperacion:
    settings = get_settings()
    limite = limite or (16 if problemas else settings.rag_top_k)
    started = perf_counter()
    client = client or OllamaClient()
    with medir("expansion"):
        texto_lexico, conceptos = expandir_consulta(consulta)
    # Solo el embedding sale a un hilo: ninguna Session ni objeto ORM se comparte.
    # Un único cliente HTTP local puede usarse entre hilos; aquí genera solo embeddings.
    executor = ThreadPoolExecutor(max_workers=1) if settings.rag_parallel_embedding else None
    busquedas = [b for p in (problemas or []) for b in p.busquedas]
    # El vector del caso recibe conceptos; no necesita nombres, cifras ni todo el relato.
    consulta_vector = ' '.join(dict.fromkeys(' '.join(b.consulta for b in busquedas).split())) if busquedas else consulta
    future = executor.submit(copy_context().run, _preparar_vector, consulta_vector, client) if executor else None
    try:
        tick_lexical = perf_counter()
        with medir("lexical"):
            focal = not problemas and "responsabilidad contractual" in normalizar(consulta)
            if problemas:
                por_concepto = buscar_candidatos_por_conceptos(db,
                    {b.clave: b.consulta for b in busquedas}, area=area, limite=settings.rag_candidate_k)
                lexical = list({str(r.Norma.id): r for filas in por_concepto.values() for r in filas}.values())
            else:
                lexical = buscar_candidatos(db, texto_lexico, area=area,
                    limite=settings.rag_candidate_k * 4 if focal else settings.rag_candidate_k)
            if focal:
                lexical = [r for r in lexical if pertinencia_suficiente(consulta, r.Norma)]
                lexical.sort(key=lambda r: (-_prioridad_conceptual(r.Norma), -float(r.relevancia)))
                lexical = lexical[:settings.rag_candidate_k]
        lexical_ms = (perf_counter()-tick_lexical)*1000
    except BaseException:
        if executor:
            executor.shutdown(wait=True, cancel_futures=True)
        raise
    semantic = []
    warning = None
    tick = perf_counter()
    try:
        vector, digest = future.result() if future else _preparar_vector(consulta_vector, client)
        # Savepoint evita dejar la sesión abortada si aún falta la migración vectorial.
        with db.begin_nested():
            semantic = _buscar_vector(db, vector, digest, settings.rag_candidate_k, area, client)
        if not semantic:
            warning = "No hay embeddings actuales; se utilizó la búsqueda léxica."
    except (IAError, SQLAlchemyError):
        warning = "El servicio local de inteligencia artificial no está disponible. Se utilizó la búsqueda léxica."
    finally:
        if executor:
            executor.shutdown(wait=True)
    semantic_ms = (perf_counter()-tick)*1000
    by_id = {str(row.Norma.id): Coincidencia(row.Norma, float(row.relevancia), rango_lexico=i)
             for i, row in enumerate(lexical, 1)}
    for row in semantic:
        key = str(row.Norma.id)
        if key in by_id:
            by_id[key].rango_semantico = row.rango_semantico
            by_id[key].similitud = row.similitud
        else:
            by_id[key] = row
    with medir("rrf"):
        fused = fusionar_rankings([[str(row.Norma.id) for row in lexical],
                                  [str(row.Norma.id) for row in semantic]])
    results = []
    por_problema = {}
    if problemas:
        scores = dict(fused)
        for problema in problemas:
            elegidos = []
            for busqueda in problema.busquedas:
                candidatos = [r for r in by_id.values() if busqueda.pertinente(r.Norma)]
                candidatos.sort(key=lambda r: (-busqueda.prioridad(r.Norma),
                    -scores.get(str(r.Norma.id), 0), r.Norma.numero_articulo))
                if candidatos:
                    row = candidatos[0]
                    clave = str(row.Norma.id)
                    if clave not in {str(r.Norma.id) for r in results} and len(results) < limite:
                        row.relevancia = scores.get(clave, 0)
                        results.append(row)
                    if clave in {str(r.Norma.id) for r in results}:
                        elegidos.append(clave)
            por_problema[problema.clave] = list(dict.fromkeys(elegidos))
        return Recuperacion(results, 'hibrida' if semantic else 'lexica',
            {'lexica': round(lexical_ms, 2), 'semantica': round(semantic_ms, 2),
             'retrieval': round((perf_counter()-started)*1000, 2)}, warning, por_problema)
    # RRF mide acuerdo entre canales, no pertinencia. El filtro posterior conserva
    # k=60 y candidate_k; una coincidencia lateral no consume el top final.
    if conceptos:
        ancla = ancla_tematica(conceptos)
        fused.sort(key=lambda item: (-afinidad_tematica(conceptos, by_id[item[0]].Norma, ancla),
                                     -item[1], item[0]))
    for key, score in fused:
        row = by_id[key]
        if not pertinencia_suficiente(consulta, row.Norma):
            continue
        row.relevancia = score
        results.append(row)
        if len(results) >= limite:
            break
    return Recuperacion(results, "hibrida" if semantic else "lexica",
        {"lexica": round(lexical_ms, 2), "semantica": round(semantic_ms, 2),
         "retrieval": round((perf_counter()-started)*1000, 2)}, warning)


# --- Recuperación por problema (casos complejos) ----------------------------------
# Un caso con mora, cláusula penal, vicios y resolución no se resuelve con una búsqueda
# genérica: cada cuestión tiene su artículo y una sola consulta promedia todo y no
# encuentra ninguno bien. Acá se busca una vez por problema y después se unifica.

FUENTES_POR_PROBLEMA = 3
MAXIMO_FUENTES_CASO = 20


def buscar_por_problemas(db: Session, problemas, area: str | None = None,
                         client: OllamaClient | None = None,
                         por_problema: int = FUENTES_POR_PROBLEMA,
                         limite: int = MAXIMO_FUENTES_CASO) -> Recuperacion:
    """Una búsqueda híbrida por cada problema jurídico, fusionadas sin duplicados.

    Cada problema aporta sus mejores normas y se registra cuáles fueron, para que la
    generación sepa qué fuentes puede citar en cada apartado. El orden final es por
    problema, no por puntaje global: así ninguna cuestión queda sin material aunque
    otra tenga coincidencias más fuertes.
    """
    settings = get_settings()
    client = client or OllamaClient()
    started = perf_counter()
    if not problemas:
        return Recuperacion([], 'lexica', {}, None, {})

    tick = perf_counter()
    with medir("lexical"):
        # Una sola consulta SQL para todos los problemas, con el índice de siempre.
        por_concepto = buscar_candidatos_por_conceptos(
            db, {p.clave: p.consulta for p in problemas if p.consulta}, area=area,
            limite=settings.rag_candidate_k)
    lexical_ms = (perf_counter() - tick) * 1000

    tick = perf_counter()
    semantico_por_problema: dict[str, list] = {}
    advertencia = None
    try:
        for problema in problemas:
            if not problema.consulta:
                continue
            vector, digest = _preparar_vector(problema.consulta, client)
            # Savepoint por problema: si falta la migración vectorial, la sesión sigue viva.
            with db.begin_nested():
                semantico_por_problema[problema.clave] = _buscar_vector(
                    db, vector, digest, settings.rag_candidate_k, area, client)
        if not any(semantico_por_problema.values()):
            advertencia = "No hay embeddings actuales; se utilizó la búsqueda léxica."
    except (IAError, SQLAlchemyError):
        semantico_por_problema = {}
        advertencia = ("El servicio local de inteligencia artificial no está disponible. "
                       "Se utilizó la búsqueda léxica.")
    semantic_ms = (perf_counter() - tick) * 1000

    normas: dict[str, Coincidencia] = {}
    resultados: list[Coincidencia] = []
    mapa: dict[str, list[str]] = {}

    candidatas: dict[str, list[tuple[str, float]]] = {}
    for problema in problemas:
        lexicos = list(por_concepto.get(problema.clave, []))
        semanticos = semantico_por_problema.get(problema.clave, [])
        for i, fila in enumerate(lexicos, 1):
            clave = str(fila.Norma.id)
            normas.setdefault(clave, Coincidencia(fila.Norma, float(fila.relevancia),
                                                  rango_lexico=i))
        for fila in semanticos:
            clave = str(fila.Norma.id)
            if clave in normas:
                normas[clave].rango_semantico = fila.rango_semantico
                normas[clave].similitud = fila.similitud
            else:
                normas[clave] = fila
        # El mismo RRF de siempre, pero dentro del problema: así compiten entre sí las
        # normas candidatas de esa cuestión y no contra las de las demás.
        with medir("rrf"):
            fusion = fusionar_rankings([[str(f.Norma.id) for f in lexicos],
                                        [str(f.Norma.id) for f in semanticos]])
        elegidas = []
        for clave, puntaje in fusion:
            if len(elegidas) >= por_problema:
                break
            fila = normas.get(clave)
            if fila is None or not fuente_pertinente(problema, fila.Norma):
                continue
            elegidas.append((clave, puntaje))
        candidatas[problema.clave] = elegidas
        mapa[problema.clave] = []
    # Una primera vuelta reserva al menos una fuente para cada problema con candidatos.
    # El tope global anterior se agotaba en los primeros apartados y dejaba vicios sin
    # ninguna fuente aun cuando había normas pertinentes recuperadas.
    for posicion in range(por_problema):
        for problema in problemas:
            opciones = candidatas.get(problema.clave, [])
            if posicion >= len(opciones):
                continue
            clave, puntaje = opciones[posicion]
            if clave not in {str(r.Norma.id) for r in resultados}:
                if len(resultados) >= limite:
                    continue
                fila = normas[clave]
                fila.relevancia = puntaje
                resultados.append(fila)
            mapa[problema.clave].append(clave)

    return Recuperacion(
        resultados, 'hibrida' if any(semantico_por_problema.values()) else 'lexica',
        {'lexica': round(lexical_ms, 2), 'semantica': round(semantic_ms, 2),
         'retrieval': round((perf_counter() - started) * 1000, 2)}, advertencia, mapa)
