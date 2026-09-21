from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.models.shared.enums import EstadoVigencia, TipoDocumento
from typing import Literal


class Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FuenteIA(Estricto):
    id: UUID
    codigo: str
    numero_articulo: int
    articulo: str
    epigrafe: str | None
    texto: str
    version: int
    estado_vigencia: EstadoVigencia
    fuente_nombre: str
    fuente_url: str
    contenido_hash: str
    relevancia: float = 0
    rango_lexico: int | None = None
    rango_semantico: int | None = None
    similitud: float | None = None


class BusquedaIAResponse(Estricto):
    consulta: str
    modo: str
    resultados: list[FuenteIA]
    tiempos_ms: dict[str, float]
    advertencia: str | None


class ActorIA(Estricto):
    rol: str = Field(min_length=2, max_length=60)
    nombre: str | None = None
    evidencia: str = Field(min_length=2, max_length=300)


class RelacionIA(Estricto):
    relacion: str = Field(max_length=100)
    evidencia: str = Field(min_length=2, max_length=300)


class ContextoIA(Estricto):
    # El orden es significativo: la generación con esquema es secuencial, así que el modelo
    # copia primero los hechos literales y solo después deriva roles y relaciones de ellos.
    hechos: list[str] = Field(default_factory=list, max_length=24)
    actores: list[ActorIA] = Field(default_factory=list, max_length=6)
    relaciones: list[RelacionIA] = Field(default_factory=list, max_length=6)
    conceptos: list[str] = Field(default_factory=list, max_length=8)


class EvidenciaModelo(Estricto):
    fuente: str = Field(pattern=r"^F[1-9][0-9]*$")
    cita: str = Field(min_length=12, max_length=600)
    # Un análisis de caso complejo desarrolla hecho, regla y aplicación: 900 caracteres
    # obligaban a resumirlo en una etiqueta.
    explicacion: str = Field(min_length=5, max_length=2600)


class RespuestaModelo(Estricto):
    # "suficiente" va después del análisis: declarar la suficiencia antes de reunir los
    # fundamentos obligaba al modelo a decidir a ciegas y producía abstenciones erróneas.
    resumen: str = Field(max_length=1600)
    analisis: list[EvidenciaModelo] = Field(max_length=20)
    suficiente: bool
    conclusion: str = Field(max_length=2600)
    limitaciones: list[str] = Field(max_length=6)


class RespuestaConContexto(RespuestaModelo):
    # Una llamada produce respuesta y HU-02; el contexto se verifica por separado.
    contexto: ContextoIA


class FundamentoSeleccionado(Estricto):
    cita_id: str = Field(pattern=r"^F[1-9][0-9]*C[1-9][0-9]*$")
    explicacion: str = Field(min_length=5, max_length=1200)


class RespuestaSeleccion(Estricto):
    # Extraer primero: impide que el modelo recicle su análisis como supuesto hecho.
    contexto: ContextoIA
    resumen: str = Field(max_length=1200)
    # El número de fundamentos lo fijan los problemas jurídicos del caso, no un tope
    # de rendimiento: antes eran 3 y eso recortaba análisis legítimos.
    analisis: list[FundamentoSeleccionado] = Field(max_length=10)
    suficiente: bool
    conclusion: str = Field(max_length=2000)
    limitaciones: list[str] = Field(max_length=6)


class RespuestaSimpleModelo(Estricto):
    """Una respuesta natural y los fragmentos del corpus que la respaldan."""
    respuesta: str = Field(min_length=20, max_length=6000)
    citas: list[str] = Field(default_factory=list, max_length=8)


class AnalisisProblemaModelo(Estricto):
    pregunta_id: str = Field(pattern=r"^q[1-9][0-9]*$")
    problema: str = Field(max_length=90)
    estado: Literal["fundamentado", "sin_fuente_suficiente"]
    hechos_usados: list[str] = Field(default_factory=list, max_length=24)
    derivaciones_usadas: list[str] = Field(default_factory=list, max_length=6)
    citas: list[str] = Field(default_factory=list, max_length=6)
    regla: str = Field(max_length=1100)
    aplicacion: str = Field(min_length=10, max_length=1600)
    conclusion: str = Field(min_length=10, max_length=900)

    @property
    def explicacion(self) -> str:
        partes = []
        if self.regla.strip():
            partes.append("Regla: " + self.regla.strip())
        partes.extend(("Aplicación: " + self.aplicacion.strip(),
                       "Conclusión: " + self.conclusion.strip()))
        return "\n\n".join(partes)


class RespuestaCasoComplejo(Estricto):
    # Los hechos ya se conservaron literalmente; no gastar otra generación copiándolos.
    # resumen y conclusion sí se piden: sin ellas la respuesta quedaba como una lista de
    # apartados sueltos, sin entrada ni cierre.
    resumen: str = Field(default="", max_length=1600)
    analisis: list[AnalisisProblemaModelo] = Field(max_length=14)
    conclusion: str = Field(default="", max_length=2600)
    limitaciones: list[str] = Field(default_factory=list, max_length=6)


class ProblemaModelo(Estricto):
    """Un problema jurídico independiente detectado en el relato."""
    titulo: str = Field(min_length=4, max_length=90)
    # Términos de búsqueda normativa en vocabulario jurídico general: no nombres
    # propios, cifras ni fechas del caso, que no aparecen en el articulado.
    consulta: str = Field(min_length=4, max_length=180)


class DescomposicionModelo(Estricto):
    problemas: list[ProblemaModelo] = Field(default_factory=list, max_length=10)


class RevisionModelo(Estricto):
    """Control de coherencia sobre la respuesta ya redactada."""
    # Índices (base 0) de limitaciones que contradicen los hechos o no aportan.
    limitaciones_irrelevantes: list[int] = Field(default_factory=list, max_length=8)
    # Títulos de problemas detectados que la respuesta no llegó a tratar.
    problemas_omitidos: list[str] = Field(default_factory=list, max_length=10)
    coherente: bool


class ClausulaGenerada(Estricto):
    titulo: str = Field(min_length=3, max_length=80)
    texto: str = Field(min_length=15, max_length=1200)


class CampoActualizado(Estricto):
    clave: str = Field(max_length=60)
    valor: str = Field(max_length=300)


class BorradorModelo(Estricto):
    clausulas: list[ClausulaGenerada] = Field(min_length=1, max_length=8)
    # Solo se usa al revisar: si el cambio afecta un dato del encabezado, el documento
    # entero debe quedar coherente en lugar de contradecirse entre cláusula y cabecera.
    datos_actualizados: list[CampoActualizado] = Field(default_factory=list, max_length=12)


class BorradorIA(Estricto):
    disponible: bool
    tipo_documento: TipoDocumento | None = None
    contenido: str | None = None
    clausulas: list[ClausulaGenerada] = Field(default_factory=list)
    campos_faltantes: list[str] = Field(default_factory=list)
    fuentes: list[FuenteIA] = Field(default_factory=list)
    motivo: str | None = None
    # Si el borrador no se pudo validar: la regla que falló, lo que la disparó (una palabra, una cifra) y
    # la cláusula donde apareció. Permite decirle al usuario QUÉ pasó en vez de un error genérico.
    motivo_codigo: str | None = None
    detalle_rechazo: str | None = None
    clausula_rechazada: str | None = None
    trazabilidad: dict = Field(default_factory=dict)


# --- Interpretación de un pedido en lenguaje natural (HU-14 por prompt) -----------
# El modelo solo relaciona frases con campos de la plantilla y copia el valor literal;
# no redacta el documento ni completa lo que el usuario no dijo.

class DatoExtraido(Estricto):
    campo: str = Field(max_length=60)
    valor: str = Field(max_length=300)
    # El fragmento del texto del usuario del que sale el valor. Sirve para comprobar
    # que el dato estaba escrito y para mostrarle de dónde se sacó.
    evidencia: str = Field(default="", max_length=300)
    # True solo cuando la frase pide expresamente cambiar un valor ("cambiá el plazo a…").
    reemplazar: bool = False


class ExtraccionModelo(Estricto):
    """Lo que devuelve Qwen. Vacío significa que no reconoció el tipo o no halló datos."""
    tipo_documento: Literal["", "compraventa", "arrendamiento", "prestamo"] = ""
    datos: list[DatoExtraido] = Field(default_factory=list, max_length=14)


class ExplicacionModelo(Estricto):
    explicacion: str = Field(min_length=20, max_length=900)
    ejemplo: str = Field(default="", max_length=400)


class ExplicacionArticuloIA(Estricto):
    disponible: bool
    articulo: str
    texto_original: str
    explicacion: str | None = None
    ejemplo: str | None = None
    fuente: FuenteIA | None = None
    motivo: str | None = None
    trazabilidad: dict = Field(default_factory=dict)


class ObservacionModelo(Estricto):
    # La evidencia va primero: obliga a anclar la observación en el texto antes de redactarla.
    evidencia: str = Field(min_length=6, max_length=400)
    observacion: str = Field(min_length=10, max_length=400)
    fuente: str | None = Field(default=None, pattern=r"^F[1-9][0-9]*$")


class AnalisisContratoModelo(Estricto):
    resumen: str = Field(max_length=800)
    observaciones: list[ObservacionModelo] = Field(default_factory=list, max_length=5)


class ObservacionIA(Estricto):
    """Observación redactada por el modelo. Nunca es un riesgo del motor determinista."""
    origen: Literal["ia"] = "ia"
    observacion: str
    evidencia: str
    norma_id: UUID | None = None


class AnalisisContratoIA(Estricto):
    disponible: bool
    resumen: str | None = None
    observaciones: list[ObservacionIA] = Field(default_factory=list)
    fuentes: list[FuenteIA] = Field(default_factory=list)
    motivo: str | None = None
    trazabilidad: dict = Field(default_factory=dict)


class FundamentoIA(Estricto):
    # Problema jurídico al que pertenece este fundamento; permite agrupar la respuesta
    # por tema en vez de dejar una lista de fuentes suelta al final.
    problema: str | None = None
    norma_id: UUID | None = None
    cita_textual: str
    explicacion: str


class FragmentoDocumentoIA(Estricto):
    """Un trozo del documento del usuario, citado como evidencia de la respuesta."""
    etiqueta: str
    texto: str


class RespuestaDocumentoModelo(Estricto):
    """Lo que devuelve Qwen al preguntarle sobre un documento.

    El orden importa: la generacion con esquema es secuencial, asi que `encontrado` va
    al final, despues de redactar. Declararlo primero obliga al modelo a decidir a
    ciegas y produce negativas falsas sobre datos que si estaban en el documento; es el
    mismo motivo por el que `suficiente` va despues del analisis en RespuestaModelo.
    """
    respuesta: str = Field(default="", max_length=1200)
    fragmentos_usados: list[str] = Field(default_factory=list, max_length=6)
    encontrado: bool


class RespuestaJuridicaIA(Estricto):
    estado: Literal["fundamentada", "insuficiente", "no_disponible", "error_validacion"]
    resumen_caso: str
    area_juridica: str | None = None
    contexto: ContextoIA = Field(default_factory=ContextoIA)
    analisis: list[FundamentoIA] = Field(default_factory=list)
    conclusion: str
    articulos_utilizados: list[UUID] = Field(default_factory=list)
    fuentes: list[FuenteIA] = Field(default_factory=list)
    # Evidencia tomada del documento del usuario, cuando la consulta era sobre uno.
    # Es independiente de `fuentes`, que siempre son normas.
    fuentes_documento: list[FragmentoDocumentoIA] = Field(default_factory=list)
    documento_nombre: str | None = None
    limitaciones: list[str] = Field(default_factory=list)
    trazabilidad: dict = Field(default_factory=dict)
