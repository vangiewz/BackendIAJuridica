from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc, Row, literal_column, literal, union_all
from types import SimpleNamespace
from app.models.conocimiento.norma import Norma

# `busqueda` se declara en la migracion, no en el modelo (ver el comentario en norma.py).
BUSQUEDA = literal_column("normas.busqueda")


def _construir_tsquery(db: Session, consulta: str):
    """Arma el tsquery de la consulta del usuario, o None si no quedo ningun termino util."""
    # Los lexemas salen del mismo analizador que llena la columna `busqueda`: mismo stemming,
    # sin acentos y sin palabras vacias. Si no queda ninguno, la consulta era solo signos.
    lexemas = db.scalar(select(func.tsvector_to_array(func.to_tsvector('es_unaccent', consulta))))
    if not lexemas:
        return None

    # Se unen con OR, no con AND. `websearch_to_tsquery` exige TODOS los terminos, y una
    # pregunta en lenguaje natural —"el vendedor no me transfiere el terreno"— no tiene
    # ningun articulo que los contenga todos: devolvia cero. El orden lo pone ts_rank_cd,
    # que ya premia a los articulos que aciertan mas terminos.
    comillas = "'"
    terminos = " | ".join(f"{comillas}{l.replace(comillas, comillas * 2)}{comillas}" for l in lexemas)
    return func.to_tsquery('es_unaccent', terminos)


def buscar(db: Session, consulta: str, area: str | None = None, limite: int = 20, desplazamiento: int = 0) -> tuple[int, list[Row]]:
    """Full-text en espanol sobre normas activas, ordenado por relevancia."""
    query_ts = _construir_tsquery(db, consulta)
    if query_ts is None:
        return 0, []

    rank = func.ts_rank_cd(BUSQUEDA, query_ts).label('relevancia')
    headline = func.ts_headline(
        'es_unaccent', Norma.texto, query_ts, 'MaxWords=40, MinWords=15'
    ).label('fragmento')

    stmt = (
        select(Norma, rank, headline)
        .where(Norma.activa == True)
        .where(BUSQUEDA.op('@@')(query_ts))
    )
    if area:
        stmt = stmt.where(Norma.area_juridica == area)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    if total == 0:
        return 0, []

    # El desempate por numero_articulo es lo que hace estable la paginacion: sin el, dos
    # busquedas iguales pueden devolver distinto orden entre resultados de igual relevancia.
    stmt = (
        stmt.order_by(desc('relevancia'), Norma.numero_articulo.asc())
        .limit(limite)
        .offset(desplazamiento)
    )
    return total, db.execute(stmt).all()


def buscar_candidatos(db: Session, consulta: str, area=None, limite=20):
    """Mismo ranking para RAG, sin COUNT ni ts_headline que RRF no utiliza."""
    query_ts = _construir_tsquery(db, consulta)
    if query_ts is None:
        return []
    rank = func.ts_rank_cd(BUSQUEDA, query_ts).label("relevancia")
    stmt = select(Norma, rank).where(Norma.activa.is_(True), BUSQUEDA.op("@@")(query_ts))
    if area:
        stmt = stmt.where(Norma.area_juridica == area)
    return db.execute(stmt.order_by(desc("relevancia"), Norma.numero_articulo.asc()).limit(limite)).all()


def buscar_candidatos_por_conceptos(db: Session, consultas: dict[str, str], area=None, limite=20):
    """Mismo índice de texto completo; una consulta SQL para todos los subproblemas."""
    sentencias = []
    for clave, consulta in consultas.items():
        query = func.websearch_to_tsquery('es_unaccent', ' OR '.join(consulta.split()))
        rank = func.ts_rank_cd(BUSQUEDA, query).label('relevancia')
        stmt = select(Norma.id.label('norma_id'), literal(clave).label('concepto'), rank).where(
            Norma.activa.is_(True), BUSQUEDA.op('@@')(query))
        if area:
            stmt = stmt.where(Norma.area_juridica == area)
        sentencias.append(stmt.order_by(desc('relevancia'), Norma.numero_articulo).limit(limite))
    if not sentencias:
        return {}
    filas = db.execute(union_all(*sentencias)).all()
    normas = {n.id: n for n in db.scalars(select(Norma).where(Norma.id.in_({f.norma_id for f in filas})))}
    resultado = {clave: [] for clave in consultas}
    for fila in filas:
        resultado[fila.concepto].append(SimpleNamespace(Norma=normas[fila.norma_id], relevancia=fila.relevancia))
    return resultado
