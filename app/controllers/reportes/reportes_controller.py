"""Reporte dinámico: interpretar la petición y ejecutarla contra los datos del usuario.

Solo lectura. Nada de lo que hay aquí escribe en la base: el reporte se calcula y se
devuelve, no se persiste.
"""
from time import perf_counter
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.reportes.esquemas import (
    EspecificacionReporte, FormatoExportacion, ReporteResultado,
)
from app.services.reportes import exportadores, query_builder
from app.services.reportes.catalogo import (
    ENTIDADES, FUNCIONES, MENSAJE_FUERA_DE_ALCANCE, OPERADORES_POR_TIPO, VISUALIZACIONES,
)
from app.services.reportes.fechas import RELATIVAS
from app.services.reportes.interprete import ReporteNoDisponibleError, interpretar
from app.services.reportes.query_builder import ETIQUETA_FUNCION, ReporteInvalido


class ReporteNoInterpretableError(Exception):
    """La petición no se puede expresar con el catálogo; el mensaje explica qué sí se puede."""


def generar_reporte(db: Session, usuario_id: UUID, peticion: str,
                    actual: EspecificacionReporte | None = None,
                    client=None) -> ReporteResultado:
    if not get_settings().ia_enabled:
        raise ReporteNoDisponibleError("La función de IA está desactivada.")

    inicio = perf_counter()
    # La validación arma la consulta sin ejecutarla: si un nombre no existe, el intérprete
    # se entera antes de tocar la base y puede corregir con el modelo.
    spec = interpretar(peticion, actual,
                       validar=lambda propuesta: query_builder.preparar(propuesta, usuario_id),
                       client=client)
    interpretacion_ms = int((perf_counter() - inicio) * 1000)

    if not spec.entidad:
        raise ReporteNoInterpretableError(spec.aclaracion or MENSAJE_FUERA_DE_ALCANCE)

    inicio = perf_counter()
    try:
        resultado = query_builder.ejecutar(db, spec, usuario_id)
    except ReporteInvalido as exc:
        raise ReporteNoInterpretableError(str(exc)) from None

    resultado.interpretacion_ms = interpretacion_ms
    resultado.consulta_ms = int((perf_counter() - inicio) * 1000)
    # El formato pedido en la frase viaja al frontend para que lance esa descarga; el
    # reporte se muestra igual, pedir un archivo no reemplaza verlo en pantalla.
    resultado.exportacion = spec.exportacion
    resultado.peticion = peticion
    return resultado


def ejecutar_especificacion(db: Session, usuario_id: UUID,
                            spec: EspecificacionReporte) -> ReporteResultado:
    """Ejecuta una especificación ya estructurada, sin pasar por el modelo de lenguaje.

    Es la puerta del constructor visual y la base de la exportación. La especificación
    llega del cliente, así que se revalida entera contra el catálogo y la consulta se
    arma con el usuario del token: no hay atajo que evite ninguna de las dos cosas.
    """
    inicio = perf_counter()
    try:
        resultado = query_builder.ejecutar(db, spec, usuario_id)
    except ReporteInvalido as exc:
        raise ReporteNoInterpretableError(str(exc)) from None
    resultado.consulta_ms = int((perf_counter() - inicio) * 1000)
    return resultado


def exportar_reporte(db: Session, usuario_id: UUID, spec: EspecificacionReporte,
                     formato: FormatoExportacion,
                     peticion: str = "") -> tuple[bytes, str, str]:
    """Rehace la consulta y devuelve (contenido, nombre de archivo, tipo MIME).

    No interviene el modelo de lenguaje: la especificación ya fue interpretada. Lo que
    sí se repite es la validación completa contra el catálogo y el filtro por usuario,
    porque la especificación vuelve desde el cliente y no se le concede confianza.
    """
    resultado = ejecutar_especificacion(db, usuario_id, spec)
    resultado.peticion = peticion
    contenido = exportadores.generar(resultado, formato)
    return (contenido, exportadores.nombre_de_archivo(resultado, formato),
            exportadores.TIPOS_MIME[formato])


def describir_catalogo() -> dict:
    """Todo lo que el constructor visual necesita saber, tomado del catálogo real.

    Incluye por campo qué se puede hacer con él (filtrar, ordenar, agrupar, agregar) y
    con qué operadores, para que el frontend no tenga una segunda copia de esas reglas
    que se desincronice. Un campo nuevo en `catalogo.py` aparece aquí sin tocar nada más.
    """
    entidades = [{
        "entidad": nombre,
        "etiqueta": entidad.etiqueta,
        "descripcion": entidad.descripcion,
        "columnas_por_defecto": list(entidad.por_defecto),
        "campos": [{
            "clave": clave,
            "etiqueta": campo.etiqueta,
            "tipo": campo.tipo,
            "filtrable": campo.filtrable,
            "ordenable": campo.ordenable,
            "agrupable": campo.agrupable,
            "agregable": campo.agregable,
            "valores": list(campo.valores),
            "operadores": list(OPERADORES_POR_TIPO.get(campo.tipo, ()))
                          if campo.filtrable else [],
        } for clave, campo in entidad.campos.items()],
    } for nombre, entidad in ENTIDADES.items()]

    return {
        "entidades": entidades,
        "funciones": [{"clave": funcion, "etiqueta": ETIQUETA_FUNCION[funcion]}
                      for funcion in FUNCIONES],
        "visualizaciones": [{"clave": v, "etiqueta": v.capitalize()}
                            for v in VISUALIZACIONES],
        "direcciones": [{"clave": "asc", "etiqueta": "Menor a mayor"},
                        {"clave": "desc", "etiqueta": "Mayor a menor"}],
        # El backend sigue siendo el único que interpreta fechas; esto es solo la ayuda
        # que se le muestra al usuario.
        "expresiones_fecha": list(RELATIVAS),
    }
