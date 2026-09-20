"""De una especificación validada a una consulta SQLAlchemy.

Aquí no llega nada del modelo de lenguaje que no haya pasado por el catálogo: cada
nombre se resuelve contra `catalogo.ENTIDADES` y lo que no está se rechaza. Los valores
del usuario viajan siempre como parámetros ligados, nunca concatenados en el SQL.

El módulo es de solo lectura: solo construye `select()`. No hay insert, update ni delete.
"""
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.reportes.esquemas import (
    AgregacionReporte, ColumnaReporte, EspecificacionReporte, FiltroReporte,
    ReporteResultado,
)
from app.services.reportes import fechas
from app.services.reportes.catalogo import (
    ENUMERADO, FECHA, LISTA, MENSAJE_FUERA_DE_ALCANCE, NUMERO, RUTA_DETALLE, Campo,
    Entidad, obtener_entidad,
)

LIMITE_MAXIMO = 500
LIMITE_POR_DEFECTO = 100
CLAVE_ID = "_id"

ETIQUETA_FUNCION = {"conteo": "Cantidad", "suma": "Suma", "promedio": "Promedio",
                    "minimo": "Mínimo", "maximo": "Máximo"}


class ReporteInvalido(Exception):
    """La especificación no se puede ejecutar con el catálogo permitido."""


def _campo(entidad: Entidad, nombre: str) -> Campo:
    campo = entidad.campos.get((nombre or "").strip().lower())
    if campo is None:
        disponibles = ", ".join(sorted(entidad.campos))
        raise ReporteInvalido(
            f"El campo «{nombre}» no existe en {entidad.etiqueta.lower()}. "
            f"Campos disponibles: {disponibles}.")
    return campo


# --- Filtros ---------------------------------------------------------------------
# Un filtro que no se entiende detiene el reporte, nunca se descarta en silencio: si
# alguien pide "solo los de riesgo alto" y el filtro se pierde, vería todos los riesgos
# creyendo que son los altos. Las columnas y el orden sí se pueden ajustar sin engañar.

def _valor_numerico(texto: str, campo_nombre: str) -> float:
    try:
        return float(str(texto).strip().replace(",", "."))
    except (TypeError, ValueError):
        raise ReporteInvalido(
            f"«{texto}» no es un número válido para {campo_nombre}.") from None


def _valor_enumerado(texto: str, campo: Campo, campo_nombre: str) -> str:
    valor = str(texto).strip().lower()
    if valor not in campo.valores:
        raise ReporteInvalido(
            f"«{texto}» no es un valor de {campo.etiqueta.lower()}. "
            f"Valores posibles: {', '.join(campo.valores)}.")
    return valor


def _condicion_fecha(campo: Campo, filtro: FiltroReporte, ahora: datetime,
                     descripciones: list[str]):
    expr = campo.expr
    try:
        inicio, fin = fechas.resolver(filtro.valor, ahora)
    except fechas.FechaAmbigua:
        raise ReporteInvalido(
            f"No pude interpretar «{filtro.valor}» como fecha. Podés escribirla como "
            f"2026-09, 2026-09-15, «septiembre», «este mes» o «últimos 30 días».") from None

    if filtro.operador in ("igual", "entre"):
        if filtro.operador == "entre" and filtro.valor_hasta:
            try:
                _, fin = fechas.resolver(filtro.valor_hasta, ahora)
            except fechas.FechaAmbigua:
                raise ReporteInvalido(
                    f"No pude interpretar «{filtro.valor_hasta}» como fecha.") from None
            descripciones.append(
                f"{campo.etiqueta}: entre {filtro.valor} y {filtro.valor_hasta}")
        else:
            descripciones.append(
                f"{campo.etiqueta}: {fechas.describir(filtro.valor, inicio, fin)}")
        return expr.is_not(None) & (expr >= inicio) & (expr < fin)
    if filtro.operador in ("desde", "mayor_que"):
        descripciones.append(f"{campo.etiqueta}: desde {filtro.valor}")
        return expr >= (inicio if filtro.operador == "desde" else fin)
    if filtro.operador in ("hasta", "menor_que"):
        descripciones.append(f"{campo.etiqueta}: hasta {filtro.valor}")
        return expr < (fin if filtro.operador == "hasta" else inicio)
    if filtro.operador == "distinto":
        descripciones.append(f"{campo.etiqueta}: fuera de {filtro.valor}")
        return (expr < inicio) | (expr >= fin)
    raise ReporteInvalido(
        f"El operador «{filtro.operador}» no se puede aplicar a una fecha.")


def _condicion(entidad: Entidad, filtro: FiltroReporte, ahora: datetime,
               descripciones: list[str]):
    campo = _campo(entidad, filtro.campo)
    if not campo.filtrable:
        raise ReporteInvalido(f"No se puede filtrar por {campo.etiqueta.lower()}.")
    if campo.tipo == FECHA:
        return _condicion_fecha(campo, filtro, ahora, descripciones)

    expr, operador = campo.expr, filtro.operador
    if operador == "contiene":
        if campo.tipo == LISTA:
            raise ReporteInvalido(f"No se puede buscar texto dentro de {campo.etiqueta}.")
        descripciones.append(f"{campo.etiqueta} contiene «{filtro.valor}»")
        # icontains parametriza el valor y escapa los comodines: el texto del usuario
        # nunca se concatena al SQL.
        return expr.icontains(filtro.valor, autoescape=True)

    if campo.tipo == NUMERO:
        valor: Any = _valor_numerico(filtro.valor, campo.etiqueta.lower())
    elif campo.tipo == ENUMERADO:
        valor = _valor_enumerado(filtro.valor, campo, filtro.campo)
    else:
        valor = str(filtro.valor).strip()

    if operador == "igual":
        descripciones.append(f"{campo.etiqueta} = {valor}")
        return expr == valor
    if operador == "distinto":
        descripciones.append(f"{campo.etiqueta} ≠ {valor}")
        return (expr != valor) | expr.is_(None)
    if operador in ("mayor_que", "desde"):
        simbolo = "≥" if operador == "desde" else ">"
        descripciones.append(f"{campo.etiqueta} {simbolo} {valor}")
        return expr >= valor if operador == "desde" else expr > valor
    if operador in ("menor_que", "hasta"):
        simbolo = "≤" if operador == "hasta" else "<"
        descripciones.append(f"{campo.etiqueta} {simbolo} {valor}")
        return expr <= valor if operador == "hasta" else expr < valor
    if operador == "entre":
        if campo.tipo != NUMERO:
            raise ReporteInvalido(f"«entre» solo aplica a números y fechas, no a "
                                  f"{campo.etiqueta.lower()}.")
        hasta = _valor_numerico(filtro.valor_hasta, campo.etiqueta.lower())
        descripciones.append(f"{campo.etiqueta}: entre {valor} y {hasta}")
        return expr.between(valor, hasta)
    raise ReporteInvalido(f"El operador «{filtro.operador}» no está permitido.")


# --- Agregaciones ----------------------------------------------------------------

def _agregacion(entidad: Entidad, agregacion: AgregacionReporte):
    """Devuelve (clave, etiqueta, expresión). Solo funciones y campos autorizados."""
    if agregacion.funcion == "conteo" and not agregacion.campo:
        return "conteo", "Cantidad", func.count(entidad.modelo.id)

    campo = _campo(entidad, agregacion.campo)
    if agregacion.funcion == "conteo":
        return (f"conteo_{agregacion.campo}", f"Cantidad de {campo.etiqueta.lower()}",
                func.count(campo.expr))
    if not campo.agregable:
        raise ReporteInvalido(
            f"No se puede calcular {ETIQUETA_FUNCION[agregacion.funcion].lower()} "
            f"sobre {campo.etiqueta.lower()}: no es un campo numérico agregable.")
    funciones = {"suma": func.sum, "promedio": func.avg,
                 "minimo": func.min, "maximo": func.max}
    clave = f"{agregacion.funcion}_{agregacion.campo}"
    etiqueta = f"{ETIQUETA_FUNCION[agregacion.funcion]} de {campo.etiqueta.lower()}"
    return clave, etiqueta, funciones[agregacion.funcion](campo.expr)


# --- Construcción ----------------------------------------------------------------

class Plan:
    """La consulta lista para ejecutar y lo que hay que contarle al usuario sobre ella."""

    def __init__(self, entidad: Entidad, spec: EspecificacionReporte, stmt: Select,
                 columnas: list[ColumnaReporte], filtros: list[str], avisos: list[str],
                 con_id: bool):
        self.entidad = entidad
        self.spec = spec
        self.stmt = stmt
        self.columnas = columnas
        self.filtros = filtros
        self.avisos = avisos
        self.con_id = con_id


def preparar(spec: EspecificacionReporte, usuario_id: UUID,
             ahora: datetime | None = None) -> Plan:
    ahora = ahora or datetime.now(timezone.utc)
    avisos: list[str] = []
    try:
        entidad = obtener_entidad(spec.entidad)
    except KeyError:
        raise ReporteInvalido(MENSAJE_FUERA_DE_ALCANCE) from None

    agrupacion = [nombre for nombre in spec.agrupacion if nombre]
    agregaciones = list(spec.agregaciones)
    seleccion: list[tuple[str, str, str, Any]] = []   # clave, etiqueta, tipo, expresión

    if agrupacion:
        for nombre in agrupacion:
            campo = _campo(entidad, nombre)
            if not campo.agrupable:
                raise ReporteInvalido(
                    f"No se puede agrupar por {campo.etiqueta.lower()}.")
            seleccion.append((nombre, campo.etiqueta, campo.tipo, campo.expr))
        # Agrupar sin decir qué se calcula es contar.
        if not agregaciones:
            agregaciones = [AgregacionReporte(funcion="conteo")]

    for agregacion in agregaciones:
        clave, etiqueta, expr = _agregacion(entidad, agregacion)
        seleccion.append((clave, etiqueta, NUMERO, expr))

    if not seleccion:
        pedidas = [nombre for nombre in spec.columnas if nombre]
        validas = []
        for nombre in pedidas:
            campo = entidad.campos.get((nombre or "").strip().lower())
            if campo is None:
                # La columna pedida se descarta sola, sin sustituirla por ninguna
                # parecida, y se avisa. No cambia qué filas se ven, solo qué se muestra.
                avisos.append(f"El campo «{nombre}» no está disponible en "
                              f"{entidad.etiqueta.lower()}; se omitió.")
                continue
            validas.append((nombre.strip().lower(), campo))
        if not validas:
            if pedidas:
                avisos.append("Ninguna de las columnas pedidas existe; se muestran las "
                              "columnas habituales de esta entidad.")
            validas = [(nombre, entidad.campos[nombre]) for nombre in entidad.por_defecto]
        for nombre, campo in validas:
            seleccion.append((nombre, campo.etiqueta, campo.tipo, campo.expr))

    etiquetados = {clave: expr.label(clave) for clave, _, _, expr in seleccion}
    columnas = [ColumnaReporte(clave=clave, etiqueta=etiqueta, tipo=tipo)
                for clave, etiqueta, tipo, _ in seleccion]

    # El id solo viaja en el listado plano de una entidad con pantalla propia, para poder
    # abrir la fila. En un agrupado no existe "la fila" que abrir.
    con_id = not agrupacion and not agregaciones and spec.entidad in RUTA_DETALLE
    expresiones = list(etiquetados.values())
    if con_id:
        expresiones.append(entidad.modelo.id.label(CLAVE_ID))

    stmt = select(*expresiones).select_from(entidad.modelo)
    if entidad.joins:
        stmt = entidad.joins(stmt)

    # Aislamiento: se impone siempre y no hay forma de expresarlo en la especificación,
    # así que ni el modelo ni un cliente manipulado pueden quitarlo o cambiarlo.
    if entidad.privada:
        if entidad.filtro_usuario is None:
            raise ReporteInvalido(MENSAJE_FUERA_DE_ALCANCE)
        stmt = stmt.where(entidad.filtro_usuario(usuario_id))
    if entidad.filtro_fijo is not None:
        stmt = stmt.where(entidad.filtro_fijo)

    filtros: list[str] = []
    for filtro in spec.filtros:
        if not filtro.campo:
            continue
        stmt = stmt.where(_condicion(entidad, filtro, ahora, filtros))

    if agrupacion:
        stmt = stmt.group_by(*[etiquetados[nombre] for nombre in agrupacion])

    stmt = _ordenar(stmt, entidad, spec, agrupacion, agregaciones, etiquetados, avisos)

    limite = max(1, min(int(spec.limite or LIMITE_POR_DEFECTO), LIMITE_MAXIMO))
    stmt = stmt.limit(limite)
    spec = spec.model_copy(update={"limite": limite})

    return Plan(entidad, spec, stmt, columnas, filtros, avisos, con_id)


def _ordenar(stmt: Select, entidad: Entidad, spec: EspecificacionReporte,
             agrupacion: list[str], agregaciones: list[AgregacionReporte],
             etiquetados: dict[str, Any], avisos: list[str]) -> Select:
    """Ordena por lo pedido; lo que no se puede ordenar se descarta con aviso."""
    criterios = []
    for orden in spec.orden:
        nombre = (orden.campo or "").strip().lower()
        if not nombre:
            continue
        if nombre in etiquetados and (nombre in agrupacion or nombre not in entidad.campos):
            # Una agregación o un campo agrupado: se ordena por lo que ya se seleccionó.
            expr = etiquetados[nombre]
        else:
            campo = entidad.campos.get(nombre)
            if campo is None or not campo.ordenable:
                avisos.append(f"No se puede ordenar por «{orden.campo}»; se omitió.")
                continue
            if agrupacion and nombre not in agrupacion:
                avisos.append(f"En un reporte agrupado no se puede ordenar por "
                              f"«{orden.campo}»; se omitió.")
                continue
            expr = campo.orden()
        criterios.append(expr.desc() if orden.direccion == "desc" else expr.asc())

    if not criterios:
        if agregaciones:
            # Lo más grande primero: es lo que se espera de un ranking o un gráfico.
            clave = next(iter(k for k in etiquetados if k not in agrupacion), None)
            if clave:
                criterios = [etiquetados[clave].desc()]
        elif agrupacion:
            criterios = [etiquetados[agrupacion[0]].asc()]
        else:
            nombre, direccion = entidad.orden_por_defecto
            campo = entidad.campos[nombre]
            criterios = [campo.orden().desc() if direccion == "desc" else campo.orden().asc()]
    return stmt.order_by(*criterios)


# --- Ejecución -------------------------------------------------------------------

def _valor(dato: Any) -> Any:
    if isinstance(dato, Enum):
        return dato.value
    if isinstance(dato, datetime):
        return dato.isoformat()
    if isinstance(dato, UUID):
        return str(dato)
    if isinstance(dato, Decimal):
        return round(float(dato), 2)
    if isinstance(dato, float):
        return round(dato, 2)
    if isinstance(dato, list):
        return ", ".join(str(item) for item in dato if item not in (None, ""))
    return dato


def ejecutar(db: Session, spec: EspecificacionReporte, usuario_id: UUID,
             ahora: datetime | None = None) -> ReporteResultado:
    plan = preparar(spec, usuario_id, ahora)
    filas = [{clave: _valor(valor) for clave, valor in fila._mapping.items()}
             for fila in db.execute(plan.stmt).all()]
    avisos = list(plan.avisos)
    if len(filas) >= plan.spec.limite:
        avisos.append(f"Se muestran las primeras {plan.spec.limite} filas.")

    visualizacion = plan.spec.visualizacion
    # Un gráfico necesita una etiqueta y un número; sin eso se cae a tabla en vez de
    # dibujar algo que no representa los datos.
    if visualizacion in ("barras", "torta") and not _sirve_para_grafico(plan):
        visualizacion = "tabla"
        avisos.append("El gráfico necesita una agrupación con un valor numérico; "
                      "se muestra como tabla.")

    return ReporteResultado(
        titulo=plan.spec.titulo.strip() or _titulo_por_defecto(plan),
        entidad=plan.spec.entidad,
        entidad_etiqueta=plan.entidad.etiqueta,
        visualizacion=visualizacion,
        columnas=plan.columnas,
        filas=filas,
        total=len(filas),
        filtros_aplicados=plan.filtros,
        avisos=avisos,
        ruta_detalle=RUTA_DETALLE.get(plan.spec.entidad) if plan.con_id else None,
        especificacion=plan.spec.model_copy(update={"visualizacion": visualizacion}),
    )


def _titulo_por_defecto(plan: Plan) -> str:
    """Cuando el modelo no puso título, uno que describa lo que se está viendo.

    Solo menciona una agrupación si el reporte está realmente agrupado: un título como
    "Documentos por mes" sobre un listado de detalle describe un reporte que no existe.
    """
    etiquetas = {columna.clave: columna.etiqueta for columna in plan.columnas}
    if plan.spec.agrupacion:
        por = ", ".join(etiquetas.get(nombre, nombre).lower()
                        for nombre in plan.spec.agrupacion)
        return f"{plan.entidad.etiqueta} por {por}"
    # Un filtro de igualdad sobre un enum es lo que mejor describe un listado
    # ("Documentos: prestamo" dice más que "Documentos").
    for filtro in plan.spec.filtros:
        campo = plan.entidad.campos.get((filtro.campo or "").strip().lower())
        if campo is not None and campo.tipo == ENUMERADO and filtro.operador == "igual":
            return f"{plan.entidad.etiqueta}: {filtro.valor}"
    return plan.entidad.etiqueta


def _sirve_para_grafico(plan: Plan) -> bool:
    tipos = [columna.tipo for columna in plan.columnas]
    return len(plan.columnas) >= 2 and tipos[0] != NUMERO and NUMERO in tipos[1:]
