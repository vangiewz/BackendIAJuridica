"""Catálogo de lo que un reporte puede mirar.

Esta es la única definición de qué entidades, campos, filtros, agrupaciones y
agregaciones existen. El modelo de lenguaje solo puede nombrar cosas de aquí: no escribe
SQL, no elige columnas físicas y no decide joins. Si un nombre no está en este archivo,
el reporte no se ejecuta.

Los nombres lógicos ("cantidad_riesgos") son deliberadamente distintos de la columna
física: detrás puede haber un subselect correlacionado o un join, y la IA no necesita
—ni puede— saberlo.
"""
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import Select, case, func, literal_column, select
from sqlalchemy.orm import aliased

from app.models.conocimiento.norma import Norma
from app.models.consultas.consulta import Consulta
from app.models.consultas.fuente_legal import FuenteLegal
from app.models.contratos.riesgo import RiesgoContractual
from app.models.documentos.analisis import AnalisisDocumento
from app.models.documentos.comparacion import ComparacionDocumentos
from app.models.documentos.documento import Documento
from app.models.shared.enums import (
    AreaJuridica, EstadoProceso, EstadoVigencia, SeveridadRiesgo, TipoDocumento,
)

TEXTO, NUMERO, FECHA, ENUMERADO, LISTA = "texto", "numero", "fecha", "enumerado", "lista"


@dataclass(frozen=True, eq=False)
class Campo:
    """Un nombre que la IA puede usar y la expresión real que le corresponde."""
    etiqueta: str
    expr: Any
    tipo: str
    filtrable: bool = False
    ordenable: bool = False
    agrupable: bool = False
    agregable: bool = False
    valores: tuple[str, ...] = ()
    # Algunas columnas se ordenan por un criterio propio: la severidad va por gravedad,
    # no por orden alfabético ("alta" antes que "baja" no significa nada para el usuario).
    expr_orden: Any = None

    def orden(self):
        return self.expr if self.expr_orden is None else self.expr_orden


@dataclass(frozen=True, eq=False)
class Entidad:
    etiqueta: str
    modelo: Any
    campos: dict[str, Campo]
    por_defecto: tuple[str, ...]
    orden_por_defecto: tuple[str, str]
    # Privada: cada fila pertenece a un usuario y el filtro se impone siempre, venga lo
    # que venga en la especificación. Pública: datos globales (la normativa).
    privada: bool
    joins: Callable[[Select], Select] | None = None
    filtro_usuario: Callable[[UUID], Any] | None = None
    filtro_fijo: Any = None
    descripcion: str = ""


# --- Expresiones derivadas -------------------------------------------------------
# Todas son subconsultas correlacionadas o joins fijos definidos aquí. El literal de
# jsonpath se escribe en línea porque es una constante de este archivo, nunca un dato
# del usuario: no hay concatenación de entrada externa en ninguna expresión.

def _largo_de_lista_json(columna):
    """Cuenta elementos solo si la columna guarda de verdad una lista JSON."""
    return case((func.jsonb_typeof(columna) == "array", func.jsonb_array_length(columna)),
                else_=0)


def _textos_json(columna, jsonpath: str):
    """Los textos que hay dentro de una lista JSON, como lista de Python."""
    return func.jsonb_path_query_array(columna, literal_column(f"'{jsonpath}'"))


def _del_ultimo_analisis(expresion):
    """Valor tomado del análisis más reciente del documento de la fila."""
    return (select(expresion)
            .where(AnalisisDocumento.documento_id == Documento.id)
            .order_by(AnalisisDocumento.creado_en.desc())
            .limit(1)
            .correlate(Documento)
            .scalar_subquery())


def _riesgos_del_documento(severidad: SeveridadRiesgo | None = None):
    consulta = (select(func.count(RiesgoContractual.id))
                .select_from(RiesgoContractual)
                .join(AnalisisDocumento, RiesgoContractual.analisis_id == AnalisisDocumento.id)
                .where(AnalisisDocumento.documento_id == Documento.id))
    if severidad is not None:
        consulta = consulta.where(RiesgoContractual.severidad == severidad)
    return consulta.correlate(Documento).scalar_subquery()


def _riesgos_del_analisis(severidad: SeveridadRiesgo | None = None):
    consulta = (select(func.count(RiesgoContractual.id))
                .where(RiesgoContractual.analisis_id == AnalisisDocumento.id))
    if severidad is not None:
        consulta = consulta.where(RiesgoContractual.severidad == severidad)
    return consulta.correlate(AnalisisDocumento).scalar_subquery()


def mes_de(columna):
    """Agrupación por mes calendario, en el formato que se muestra tal cual."""
    return func.to_char(func.date_trunc("month", columna), "YYYY-MM")


_GRAVEDAD = case((RiesgoContractual.severidad == SeveridadRiesgo.ALTA, 3),
                 (RiesgoContractual.severidad == SeveridadRiesgo.MEDIA, 2), else_=1)

_VALORES_AREA = tuple(a.value for a in AreaJuridica)
_VALORES_ESTADO = tuple(e.value for e in EstadoProceso)
_VALORES_TIPO = tuple(t.value for t in TipoDocumento)
_VALORES_SEVERIDAD = tuple(s.value for s in SeveridadRiesgo)
_VALORES_VIGENCIA = tuple(v.value for v in EstadoVigencia)

# Dos vistas del mismo modelo: una comparación nombra dos documentos distintos.
_DOC_A = aliased(Documento, name="documento_a")
_DOC_B = aliased(Documento, name="documento_b")


# --- Entidades -------------------------------------------------------------------

CONSULTAS = Entidad(
    etiqueta="Consultas jurídicas",
    modelo=Consulta,
    privada=True,
    filtro_usuario=lambda uid: Consulta.usuario_id == uid,
    descripcion="Las consultas jurídicas que hizo el usuario.",
    por_defecto=("fecha", "pregunta", "area_juridica", "estado", "cantidad_fuentes"),
    orden_por_defecto=("fecha", "desc"),
    campos={
        "fecha": Campo("Fecha", Consulta.creada_en, FECHA, filtrable=True, ordenable=True),
        "pregunta": Campo("Pregunta", Consulta.texto, TEXTO, filtrable=True),
        "area_juridica": Campo("Área jurídica", Consulta.area_juridica, ENUMERADO,
                               filtrable=True, ordenable=True, agrupable=True,
                               valores=_VALORES_AREA),
        "estado": Campo("Estado", Consulta.estado, ENUMERADO, filtrable=True,
                        ordenable=True, agrupable=True, valores=_VALORES_ESTADO),
        "cantidad_fuentes": Campo(
            "Fuentes citadas",
            select(func.count(FuenteLegal.id)).where(FuenteLegal.consulta_id == Consulta.id)
            .correlate(Consulta).scalar_subquery(),
            NUMERO, filtrable=True, ordenable=True, agregable=True),
        "articulos": Campo(
            "Artículos usados",
            select(func.string_agg(FuenteLegal.articulo, ", "))
            .where(FuenteLegal.consulta_id == Consulta.id)
            .correlate(Consulta).scalar_subquery(),
            TEXTO),
        "mes": Campo("Mes", mes_de(Consulta.creada_en), TEXTO, ordenable=True, agrupable=True),
    },
)

DOCUMENTOS = Entidad(
    etiqueta="Documentos",
    modelo=Documento,
    privada=True,
    filtro_usuario=lambda uid: Documento.usuario_id == uid,
    descripcion="Los documentos que el usuario subió, con lo detectado en su análisis.",
    por_defecto=("nombre", "tipo_documento", "fecha", "estado", "cantidad_riesgos"),
    orden_por_defecto=("fecha", "desc"),
    campos={
        "nombre": Campo("Documento", Documento.nombre_archivo, TEXTO,
                        filtrable=True, ordenable=True),
        "tipo_documento": Campo("Tipo", Documento.tipo_documento, ENUMERADO, filtrable=True,
                                ordenable=True, agrupable=True, valores=_VALORES_TIPO),
        "fecha": Campo("Fecha de carga", Documento.subido_en, FECHA,
                       filtrable=True, ordenable=True),
        "fecha_analisis": Campo("Fecha de análisis",
                                _del_ultimo_analisis(AnalisisDocumento.creado_en), FECHA,
                                filtrable=True, ordenable=True),
        "estado": Campo("Estado", Documento.estado, ENUMERADO, filtrable=True,
                        ordenable=True, agrupable=True, valores=_VALORES_ESTADO),
        "cantidad_caracteres": Campo("Caracteres", Documento.cantidad_caracteres, NUMERO,
                                     filtrable=True, ordenable=True, agregable=True),
        "cantidad_clausulas": Campo(
            "Cláusulas",
            func.coalesce(_del_ultimo_analisis(
                _largo_de_lista_json(AnalisisDocumento.obligaciones)), 0),
            NUMERO, filtrable=True, ordenable=True, agregable=True),
        "cantidad_riesgos": Campo("Riesgos", _riesgos_del_documento(), NUMERO,
                                  filtrable=True, ordenable=True, agregable=True),
        "cantidad_riesgos_altos": Campo("Riesgos altos",
                                        _riesgos_del_documento(SeveridadRiesgo.ALTA), NUMERO,
                                        filtrable=True, ordenable=True, agregable=True),
        "cantidad_montos": Campo(
            "Montos detectados",
            func.coalesce(_del_ultimo_analisis(
                _largo_de_lista_json(AnalisisDocumento.montos)), 0),
            NUMERO, filtrable=True, ordenable=True, agregable=True),
        # Los importes se guardan como el fragmento exacto hallado en el texto
        # ("Bs. 2.500"), no como número: se muestran, no se suman ni se promedian.
        "montos": Campo("Montos", _del_ultimo_analisis(
            _textos_json(AnalisisDocumento.montos, "$[*].texto")), LISTA),
        "plazos": Campo("Plazos", _del_ultimo_analisis(
            _textos_json(AnalisisDocumento.hallazgos, '$[*] ? (@.tipo == "plazo").texto')),
            LISTA),
        "resumen": Campo("Resumen", _del_ultimo_analisis(AnalisisDocumento.resumen), TEXTO),
        "mes": Campo("Mes", mes_de(Documento.subido_en), TEXTO, ordenable=True, agrupable=True),
    },
)

RIESGOS = Entidad(
    etiqueta="Riesgos contractuales",
    modelo=RiesgoContractual,
    privada=True,
    # El riesgo no guarda usuario: se llega por análisis y documento. El join es fijo.
    joins=lambda stmt: (
        stmt.join(AnalisisDocumento, RiesgoContractual.analisis_id == AnalisisDocumento.id)
            .join(Documento, AnalisisDocumento.documento_id == Documento.id)),
    filtro_usuario=lambda uid: Documento.usuario_id == uid,
    descripcion="Los riesgos detectados en los documentos del usuario.",
    por_defecto=("documento", "titulo", "severidad", "codigo_regla", "fecha"),
    orden_por_defecto=("severidad", "desc"),
    campos={
        "documento": Campo("Documento", Documento.nombre_archivo, TEXTO, filtrable=True,
                           ordenable=True, agrupable=True),
        "tipo_documento": Campo("Tipo de documento", Documento.tipo_documento, ENUMERADO,
                                filtrable=True, ordenable=True, agrupable=True,
                                valores=_VALORES_TIPO),
        "titulo": Campo("Riesgo", RiesgoContractual.descripcion, TEXTO,
                        filtrable=True, ordenable=True),
        "severidad": Campo("Severidad", RiesgoContractual.severidad, ENUMERADO, filtrable=True,
                           ordenable=True, agrupable=True, valores=_VALORES_SEVERIDAD,
                           expr_orden=_GRAVEDAD),
        "codigo_regla": Campo("Regla", RiesgoContractual.codigo_regla, TEXTO, filtrable=True,
                              ordenable=True, agrupable=True),
        "explicacion": Campo("Explicación", RiesgoContractual.motivo, TEXTO, filtrable=True),
        "clausula": Campo("Cláusula", RiesgoContractual.clausula_referencia, TEXTO),
        "articulos": Campo("Artículos", RiesgoContractual.articulos, LISTA),
        "evidencia": Campo("Evidencia", RiesgoContractual.evidencia, TEXTO),
        "fecha": Campo("Fecha del análisis", AnalisisDocumento.creado_en, FECHA,
                       filtrable=True, ordenable=True),
        "mes": Campo("Mes", mes_de(AnalisisDocumento.creado_en), TEXTO,
                     ordenable=True, agrupable=True),
    },
)

ANALISIS = Entidad(
    etiqueta="Análisis contractuales",
    modelo=AnalisisDocumento,
    privada=True,
    joins=lambda stmt: stmt.join(Documento, AnalisisDocumento.documento_id == Documento.id),
    filtro_usuario=lambda uid: Documento.usuario_id == uid,
    descripcion="Cada análisis realizado sobre un documento del usuario.",
    por_defecto=("documento", "tipo_documento", "fecha", "cantidad_clausulas",
                 "cantidad_riesgos"),
    orden_por_defecto=("fecha", "desc"),
    campos={
        "documento": Campo("Documento", Documento.nombre_archivo, TEXTO, filtrable=True,
                           ordenable=True, agrupable=True),
        "tipo_documento": Campo("Tipo", Documento.tipo_documento, ENUMERADO, filtrable=True,
                                ordenable=True, agrupable=True, valores=_VALORES_TIPO),
        "fecha": Campo("Fecha", AnalisisDocumento.creado_en, FECHA,
                       filtrable=True, ordenable=True),
        "cantidad_clausulas": Campo(
            "Cláusulas", _largo_de_lista_json(AnalisisDocumento.obligaciones), NUMERO,
            filtrable=True, ordenable=True, agregable=True),
        "cantidad_riesgos": Campo("Riesgos", _riesgos_del_analisis(), NUMERO,
                                  filtrable=True, ordenable=True, agregable=True),
        "cantidad_riesgos_altos": Campo("Riesgos altos",
                                        _riesgos_del_analisis(SeveridadRiesgo.ALTA), NUMERO,
                                        filtrable=True, ordenable=True, agregable=True),
        "reglas_evaluadas": Campo("Reglas evaluadas", AnalisisDocumento.reglas_evaluadas,
                                  NUMERO, filtrable=True, ordenable=True, agregable=True),
        "cantidad_montos": Campo("Montos detectados",
                                 _largo_de_lista_json(AnalisisDocumento.montos), NUMERO,
                                 filtrable=True, ordenable=True, agregable=True),
        "montos": Campo("Montos", _textos_json(AnalisisDocumento.montos, "$[*].texto"), LISTA),
        "resumen": Campo("Resumen", AnalisisDocumento.resumen, TEXTO, filtrable=True),
        "observaciones": Campo("Observaciones", AnalisisDocumento.observaciones, TEXTO),
        "mes": Campo("Mes", mes_de(AnalisisDocumento.creado_en), TEXTO,
                     ordenable=True, agrupable=True),
    },
)

COMPARACIONES = Entidad(
    etiqueta="Comparaciones",
    modelo=ComparacionDocumentos,
    privada=True,
    joins=lambda stmt: (
        stmt.join(_DOC_A, ComparacionDocumentos.documento_a_id == _DOC_A.id)
            .join(_DOC_B, ComparacionDocumentos.documento_b_id == _DOC_B.id)),
    filtro_usuario=lambda uid: ComparacionDocumentos.usuario_id == uid,
    descripcion="Las comparaciones entre dos documentos del usuario.",
    por_defecto=("documento_a", "documento_b", "fecha", "cantidad_diferencias"),
    orden_por_defecto=("fecha", "desc"),
    campos={
        "documento_a": Campo("Documento A", _DOC_A.nombre_archivo, TEXTO,
                             filtrable=True, ordenable=True),
        "documento_b": Campo("Documento B", _DOC_B.nombre_archivo, TEXTO,
                             filtrable=True, ordenable=True),
        "fecha": Campo("Fecha", ComparacionDocumentos.creada_en, FECHA,
                       filtrable=True, ordenable=True),
        "cantidad_diferencias": Campo(
            "Diferencias",
            ComparacionDocumentos.diferencias["cantidad_cambios"].as_integer(),
            NUMERO, filtrable=True, ordenable=True, agregable=True),
        "estrategia": Campo("Estrategia",
                            ComparacionDocumentos.diferencias["estrategia"].as_string(),
                            TEXTO, filtrable=True, ordenable=True, agrupable=True),
        "mes": Campo("Mes", mes_de(ComparacionDocumentos.creada_en), TEXTO,
                     ordenable=True, agrupable=True),
    },
)

NORMATIVA = Entidad(
    etiqueta="Normativa",
    modelo=Norma,
    privada=False,
    # Dato público, pero solo la normativa activa: la inactiva no es material de reporte.
    filtro_fijo=Norma.activa.is_(True),
    descripcion="La normativa cargada en el sistema. Es información pública, no del usuario.",
    por_defecto=("codigo", "articulo", "epigrafe", "area_juridica", "estado_vigencia"),
    orden_por_defecto=("numero_articulo", "asc"),
    campos={
        "codigo": Campo("Código", Norma.codigo, TEXTO, filtrable=True, ordenable=True,
                        agrupable=True),
        "articulo": Campo("Artículo", Norma.articulo, TEXTO, filtrable=True, ordenable=True),
        "numero_articulo": Campo("Número", Norma.numero_articulo, NUMERO, filtrable=True,
                                 ordenable=True, agregable=True),
        "epigrafe": Campo("Epígrafe", Norma.epigrafe, TEXTO, filtrable=True, ordenable=True),
        "texto": Campo("Texto", Norma.texto, TEXTO, filtrable=True),
        "libro": Campo("Libro", Norma.libro, TEXTO, filtrable=True, ordenable=True,
                       agrupable=True),
        "parte": Campo("Parte", Norma.parte, TEXTO, filtrable=True, ordenable=True,
                       agrupable=True),
        "titulo": Campo("Título", Norma.titulo, TEXTO, filtrable=True, ordenable=True,
                        agrupable=True),
        "capitulo": Campo("Capítulo", Norma.capitulo, TEXTO, filtrable=True, ordenable=True,
                          agrupable=True),
        "seccion": Campo("Sección", Norma.seccion, TEXTO, filtrable=True, ordenable=True,
                         agrupable=True),
        "area_juridica": Campo("Área jurídica", Norma.area_juridica, ENUMERADO, filtrable=True,
                               ordenable=True, agrupable=True, valores=_VALORES_AREA),
        "estado_vigencia": Campo("Vigencia", Norma.estado_vigencia, ENUMERADO, filtrable=True,
                                 ordenable=True, agrupable=True, valores=_VALORES_VIGENCIA),
        "fuente_nombre": Campo("Fuente", Norma.fuente_nombre, TEXTO, filtrable=True,
                               ordenable=True, agrupable=True),
    },
)

ENTIDADES: dict[str, Entidad] = {
    "consultas": CONSULTAS,
    "documentos": DOCUMENTOS,
    "riesgos": RIESGOS,
    "analisis": ANALISIS,
    "comparaciones": COMPARACIONES,
    "normativa": NORMATIVA,
}

# Las entidades que tienen pantalla de detalle propia: el reporte devuelve el id de cada
# fila para poder abrirla, y solo para estas.
RUTA_DETALLE = {"documentos": "documento", "consultas": "consulta",
                "comparaciones": "comparacion"}

OPERADORES = ("igual", "distinto", "contiene", "mayor_que", "menor_que", "entre",
              "desde", "hasta")

# Qué operadores acepta de verdad `query_builder._condicion` para cada tipo de campo.
# El constructor visual los lee desde la API en vez de tener su propia copia, así que
# esta tabla y lo que ejecuta el builder no pueden separarse.
OPERADORES_POR_TIPO = {
    TEXTO: ("igual", "distinto", "contiene"),
    ENUMERADO: ("igual", "distinto"),
    NUMERO: ("igual", "distinto", "mayor_que", "menor_que", "desde", "hasta", "entre"),
    FECHA: ("igual", "distinto", "desde", "hasta", "mayor_que", "menor_que", "entre"),
    # Una lista JSON se muestra, no se filtra.
    LISTA: (),
}
FUNCIONES = ("conteo", "suma", "promedio", "minimo", "maximo")
VISUALIZACIONES = ("tabla", "barras", "torta", "resumen")
FORMATOS = ("pdf", "docx", "xlsx", "pptx")
DIRECCIONES = ("asc", "desc")

MENSAJE_FUERA_DE_ALCANCE = (
    "No puedo generar ese reporte con los datos disponibles. Podés pedir reportes sobre "
    "consultas, documentos, análisis, riesgos, comparaciones o normativa.")


def obtener_entidad(nombre: str) -> Entidad:
    entidad = ENTIDADES.get((nombre or "").strip().lower())
    if entidad is None:
        raise KeyError(nombre)
    return entidad
