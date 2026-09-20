"""HU-14 y HU-15: redacción asistida de borradores y sus versiones.

El esqueleto del documento y el bloque de partes se arman con los datos que dio el
usuario. El modelo solo redacta el cuerpo de cada cláusula, y lo que escribe se
contrasta contra esos datos: no puede introducir un nombre, una cédula, un monto ni
una fecha que el usuario no haya entregado.
"""
import json
import re
import unicodedata
from time import perf_counter

from sqlalchemy.orm import Session

from app.models.ia.esquemas import BorradorIA, BorradorModelo, ClausulaGenerada
from app.services.conocimiento.busqueda_hibrida import buscar_hibrida
from app.services.generacion import plantillas
from app.services.ia.fuentes import fuente_de_norma
from app.services.ia.ollama_client import IAError, OllamaClient, RespuestaInvalida
from app.services.ia.prompts import CORRECCIONES, TAREA_BORRADOR, construir_prompt
from app.services.ia.validacion import normalizar, sin_acentos, verificar_prosa
from app.services.ia.metricas import medir, pipeline, sumar, rechazo

# Palabras que empiezan oración o pertenecen al formulario del documento y no son datos.
VOCABULARIO_FIJO = {
    "el", "la", "los", "las", "un", "una", "este", "esta", "ambas", "ambos", "en", "por",
    "para", "conforme", "las partes", "primera", "segunda", "tercera", "cuarta", "quinta",
    "sexta", "septima", "clausula", "contrato", "codigo", "civil", "boliviano", "bolivia",
    "objeto", "precio", "plazo", "canon", "interes", "intereses", "entrega", "destino",
    "obligaciones", "conformidad", "falta", "si", "no", "se", "que", "de", "del", "al",
    "vendedor", "comprador", "arrendador", "arrendatario", "prestamista", "prestatario",
    "parte", "partes", "bien", "inmueble", "monto", "forma", "pago", "devolucion",
}
TOKEN_PROPIO = re.compile(r"\b[A-ZÁÉÍÓÚÑ][\wáéíóúñ]{2,}\b")


def _evidencia(datos: dict, fuentes, plantilla, instruccion=None, base=None) -> str:
    """Todo lo que el usuario ya aportó: sus datos, su instrucción y su versión anterior."""
    partes = [json.dumps(datos, ensure_ascii=False)]
    partes += [f.texto for f in fuentes]
    partes += [c.etiqueta for c in plantilla.campos] + list(plantilla.clausulas)
    partes += [plantilla.titulo, instruccion or "", base or ""]
    return ' '.join(partes)


def verificar_sin_datos_inventados(texto: str, evidencia: str) -> None:
    """Un nombre propio o una cifra que no venga del usuario ni de la norma es invención."""
    referencia = sin_acentos(evidencia)
    for token in TOKEN_PROPIO.findall(texto):
        plano = sin_acentos(token)
        if plano in VOCABULARIO_FIJO or plano in referencia:
            continue
        raise RespuestaInvalida("dato_no_proporcionado")


def verificar_marcadores(texto: str, plantilla) -> None:
    """Todo «[FALTA: …]» tiene que nombrar un campo que la plantilla realmente define.

    `campos_faltantes` se obtiene leyendo esos marcadores del texto, así que un marcador
    inventado («[FALTA: número de cuenta]») aparecería como un dato que el sistema pide.
    El detector de nombres propios no lo frena: solo mira palabras con mayúscula.
    """
    permitidas = {sin_acentos(campo.etiqueta) for campo in plantilla.campos}
    for etiqueta in plantillas.faltantes_en_contenido(texto):
        if sin_acentos(etiqueta) not in permitidas:
            raise RespuestaInvalida("campo_inexistente")


def _bloque_partes(plantilla, datos):
    lineas = []
    for campo in plantilla.campos:
        valor = str(datos.get(campo.clave, "")).strip()
        if valor or campo.obligatorio:
            lineas.append(f"{campo.etiqueta}: {valor or plantillas.marcador(campo.etiqueta)}")
    return lineas


def _ensamblar(plantilla, datos, clausulas) -> str:
    lugar = str(datos.get("lugar", "")).strip() or plantillas.marcador("Lugar de suscripción")
    fecha = str(datos.get("fecha", "")).strip() or plantillas.marcador("Fecha de suscripción")
    partes = ["\n".join([plantilla.titulo, "", "DATOS DE LAS PARTES Y DEL ACUERDO",
                         *_bloque_partes(plantilla, datos), ""])]
    ordinales = ("PRIMERA", "SEGUNDA", "TERCERA", "CUARTA", "QUINTA", "SEXTA", "SÉPTIMA", "OCTAVA")
    for i, clausula in enumerate(clausulas):
        prefijo = ordinales[i] if i < len(ordinales) else f"CLÁUSULA {i + 1}"
        partes.append(f"{prefijo}.- {clausula.titulo}\n{clausula.texto}\n")
    partes.append(f"Suscrito en {lugar}, {fecha}.\n\n"
                  "_______________________          _______________________\n"
                  "Firma                            Firma")
    return "\n".join(partes)


@pipeline
def generar_borrador(db: Session, tipo, datos: dict, instruccion: str | None = None,
                     base: str | None = None, client=None) -> BorradorIA:
    plantilla = plantillas.obtener(tipo)
    datos = {k: v for k, v in (datos or {}).items()
             if any(c.clave == k for c in plantilla.campos) and str(v).strip()}
    pendientes = plantillas.faltantes(plantilla, datos)
    client = client or OllamaClient()
    started = perf_counter()
    traza = {}
    try:
        with medir("retrieval_total"):
            recuperadas = buscar_hibrida(db, plantilla.consulta_normativa)
        fuentes = [fuente_de_norma(fila.Norma, fila) for fila in recuperadas.resultados]
        traza.update({k: v for k, v in recuperadas.tiempos_ms.items()})
    except IAError as exc:
        return BorradorIA(disponible=False, motivo=str(exc), campos_faltantes=pendientes)
    documento = {
        "TIPO": plantilla.tipo.value,
        "CLAUSULAS_REQUERIDAS": list(plantilla.clausulas),
        "DATOS_DEL_USUARIO": datos,
        # Cada dato ausente trae ya escrito el marcador exacto que debe copiarse.
        # Incluye los opcionales: si no se dieron, tampoco pueden suponerse.
        "DATOS_AUSENTES_Y_SU_MARCADOR": {c.etiqueta: plantillas.marcador(c.etiqueta)
                                         for c in plantilla.campos if not datos.get(c.clave)},
        "CLAVES_DE_DATOS": [c.clave for c in plantilla.campos],
    }
    if instruccion:
        documento["CAMBIO_SOLICITADO"] = instruccion
    if base:
        documento["VERSION_ANTERIOR"] = base[:4000]
    try:
        with medir("prompt_build"):
            messages, usadas = construir_prompt("", fuentes, documento=documento, tarea=TAREA_BORRADOR)
    except ValueError:
        return BorradorIA(disponible=False, campos_faltantes=pendientes,
                          motivo="Los datos entregados exceden el tamaño admitido.")
    evidencia = _evidencia(datos, usadas, plantilla, instruccion, base)
    for intento in range(2):
        attempt_started = perf_counter()
        if intento:
            sumar("retry_count", 1)
        try:
            generado = client.generar(messages, BorradorModelo, intentos=1)
            with medir("citation_validation"):
                for clausula in generado.clausulas:
                    verificar_prosa(clausula.texto, usadas, evidencia)
                    verificar_sin_datos_inventados(clausula.texto, evidencia)
                    verificar_marcadores(clausula.texto, plantilla)
            finales = dict(datos)
            for campo in generado.datos_actualizados:
                # Solo campos de la plantilla y solo valores que ya estaban en lo aportado.
                if any(c.clave == campo.clave for c in plantilla.campos) and campo.valor.strip():
                    verificar_prosa(campo.valor, usadas, evidencia)
                    verificar_sin_datos_inventados(campo.valor, evidencia)
                    finales[campo.clave] = campo.valor.strip()
            pendientes = plantillas.faltantes(plantilla, finales)
            traza.update({"llm_ms": round((perf_counter() - started) * 1000, 2),
                          "intentos_validacion": intento + 1})
            return BorradorIA(disponible=True, tipo_documento=plantilla.tipo,
                contenido=_ensamblar(plantilla, finales, generado.clausulas),
                campos_faltantes=pendientes, clausulas=list(generado.clausulas),
                fuentes=usadas, trazabilidad=traza)
        except RespuestaInvalida as exc:
            rechazo(exc.motivo)
            traza["validacion_motivo"] = exc.motivo
            messages = [messages[0], messages[1], {"role": "user", "content":
                "Corrección del sistema: " + CORRECCIONES.get(exc.motivo, CORRECCIONES["no_especificado"]) +
                " Reescribe todas las cláusulas cumpliendo esa regla y conserva el resto igual."}]
        except IAError as exc:
            return BorradorIA(disponible=False, motivo=str(exc), campos_faltantes=pendientes)
        finally:
            if intento:
                sumar("retry_ms", (perf_counter()-attempt_started)*1000)
    return BorradorIA(disponible=False, campos_faltantes=pendientes, trazabilidad=traza,
        motivo="El servicio local de IA devolvió una respuesta que no pudo validarse.")
