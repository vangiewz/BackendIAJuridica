"""Generación: una palabra común no es un «dato inventado», y el usuario sabe qué campo corregir.

Caso real que originó esto: un contrato de préstamo con datos correctos fallaba SIEMPRE con «el servicio
local de IA devolvió una respuesta que no pudo validarse». La causa no eran los datos: el validador tomaba
la palabra «Además», que abre una oración, por un nombre propio inventado.
"""
import json
from uuid import uuid4

import httpx
import pytest

from app.controllers.generacion import documentos_controller as controlador
from app.core.config import Settings
from app.models.generacion.esquemas import InterpretacionResponse
from app.models.ia.esquemas import BorradorIA
from app.models.shared.enums import TipoDocumento
from app.services.generacion import plantillas, revision_datos
from app.services.ia import generacion
from app.services.ia.errores import RespuestaInvalida
from app.services.ia.ollama_client import OllamaClient

PRESTAMO = plantillas.obtener(TipoDocumento.PRESTAMO)
DATOS = {
    "prestamista_nombre": "Juan Carlos Pérez", "prestamista_ci": "4587963",
    "prestatario_nombre": "María Fernanda López", "prestatario_ci": "7845126",
    "lugar": "Santa Cruz de la Sierra", "fecha": "1 de octubre de 2026", "monto": "25.000 bolivianos",
    "plazo_devolucion": "12 meses", "interes": "2% mensual", "garantia": "ninguna",
}


# --- El validador: palabras comunes vs nombres inventados ---------------------------------------

EVIDENCIA = "Juan Carlos Pérez María Fernanda López Santa Cruz de la Sierra 25.000 bolivianos"


def test_una_palabra_comun_que_abre_una_oracion_no_es_un_dato_inventado():
    texto = ("El prestamista entrega el monto acordado. Además, el prestatario se obliga a devolverlo. "
             "Asimismo, pagará los intereses.\nCada parte conserva un ejemplar.")
    generacion.verificar_sin_datos_inventados(texto, EVIDENCIA)  # no debe lanzar


def test_lo_que_abre_una_lista_tampoco_lo_es():
    generacion.verificar_sin_datos_inventados("1. Además se pagará el saldo.\n2) Finalmente firmarán.", EVIDENCIA)


def test_un_nombre_a_mitad_de_oracion_se_sigue_rechazando():
    with pytest.raises(RespuestaInvalida) as error:
        generacion.verificar_sin_datos_inventados("Además, se presta dinero a Ricardo Vargas.", EVIDENCIA)
    assert error.value.motivo == "dato_no_proporcionado"
    assert "Ricardo" in error.value.detalle and "Vargas" in error.value.detalle


def test_un_nombre_completo_que_abre_la_oracion_se_sigue_rechazando():
    with pytest.raises(RespuestaInvalida) as error:
        generacion.verificar_sin_datos_inventados("Pedro Suárez recibirá el dinero.", EVIDENCIA)
    assert "Suárez" in error.value.detalle


def test_los_nombres_que_dio_el_usuario_pasan_aunque_abran_la_oracion():
    generacion.verificar_sin_datos_inventados("Juan Carlos Pérez entrega el dinero.", EVIDENCIA)
    generacion.verificar_sin_datos_inventados("Se firma en Santa Cruz de la Sierra.", EVIDENCIA)


def test_el_rechazo_dice_que_palabras_dispararon_el_error():
    with pytest.raises(RespuestaInvalida) as error:
        generacion.verificar_sin_datos_inventados("Se firma en Cochabamba ante Ramiro Vargas.", EVIDENCIA)
    assert error.value.detalle == "Cochabamba, Ramiro, Vargas"


# --- El borrador completo: el caso real ---------------------------------------------------------

def _cliente(textos):
    """Un Ollama de mentira que responde con estas cláusulas, una respuesta por llamada."""
    respuestas = iter(textos)

    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion"]})
        if request.url.path == "/api/chat":
            clausulas = next(respuestas)
            return httpx.Response(200, json={"done": True, "message": {"content": json.dumps(
                {"clausulas": clausulas, "datos_actualizados": []}, ensure_ascii=False)}})
        return httpx.Response(200, json={"models": []})
    return OllamaClient(Settings(_env_file=None), httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def sin_retrieval(monkeypatch):
    monkeypatch.setattr(generacion, "buscar_hibrida",
                        lambda *a, **k: type("R", (), {"resultados": [], "tiempos_ms": {}})())


@pytest.fixture(autouse=True)
def ia_activa(monkeypatch):
    # El controlador se niega a generar con la IA desactivada; aquí se prueba lo que hace cuando está activa.
    monkeypatch.setattr(controlador, "get_settings", lambda: type("S", (), {"ia_enabled": True})())


def _generar(respuestas, datos=None):
    return generacion.generar_borrador(None, TipoDocumento.PRESTAMO, datos or DATOS, client=_cliente(respuestas))


def test_el_borrador_que_antes_fallaba_por_ademas_ahora_se_genera():
    borrador = _generar([[
        {"titulo": "OBJETO Y MONTO", "texto": "El prestamista entrega al prestatario el monto acordado."},
        {"titulo": "OBLIGACIONES DE LAS PARTES",
         "texto": "El prestatario devolverá el monto. Además, pagará los intereses pactados."},
    ]])
    assert borrador.disponible
    assert borrador.trazabilidad["intentos_validacion"] == 1


def test_un_rechazo_real_informa_la_palabra_y_la_clausula():
    mala = [{"titulo": "OBJETO Y MONTO", "texto": "El prestamista entrega el monto a Ricardo Lima en Oruro."}]
    borrador = _generar([mala, mala])
    assert borrador.disponible is False
    assert borrador.motivo_codigo == "dato_no_proporcionado"
    assert "Ricardo" in borrador.detalle_rechazo and "Oruro" in borrador.detalle_rechazo
    assert borrador.clausula_rechazada == "OBJETO Y MONTO"


def test_el_reintento_le_dice_al_modelo_que_palabra_no_escribir():
    enviados = []

    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion"]})
        if request.url.path == "/api/chat":
            enviados.append(json.loads(request.content)["messages"][-1]["content"])
            texto = ("El prestamista entrega el monto a Ricardo Lima." if len(enviados) == 1
                     else "El prestamista entrega el monto acordado.")
            return httpx.Response(200, json={"done": True, "message": {"content": json.dumps(
                {"clausulas": [{"titulo": "OBJETO Y MONTO", "texto": texto}], "datos_actualizados": []})}})
        return httpx.Response(200, json={"models": []})
    cliente = OllamaClient(Settings(_env_file=None), httpx.MockTransport(handler))
    borrador = generacion.generar_borrador(None, TipoDocumento.PRESTAMO, DATOS, client=cliente)
    assert borrador.disponible
    assert "Ricardo" in enviados[1] and "No lo escribas" in enviados[1]


# --- Revisión de datos: qué campo, y qué escribir -----------------------------------------------

def _por_campo(datos):
    return {p.clave: p for p in revision_datos.revisar_datos(PRESTAMO, datos)}


def test_los_datos_bien_escritos_no_generan_problemas():
    assert revision_datos.revisar_datos(PRESTAMO, DATOS) == []


def test_los_campos_del_caso_real_se_senalan_con_su_motivo():
    problemas = _por_campo({**DATOS, "lugar": "lugaR DE SUSCRIPCION SCZ", "fecha": "hoy"})
    assert set(problemas) == {"lugar", "fecha"}
    assert problemas["fecha"].nivel == "error"      # una fecha «hoy» invalida el contrato: bloquea
    assert problemas["lugar"].nivel == "aviso"      # una sigla lo afea pero no lo invalida: solo se avisa
    assert "SCZ" in problemas["lugar"].mensaje and "Santa Cruz de la Sierra" in problemas["lugar"].mensaje
    assert "lugar de suscripción" in problemas["lugar"].mensaje
    assert "no es una fecha" in problemas["fecha"].mensaje
    assert problemas["fecha"].ejemplo.startswith("1 de octubre de 2026")


@pytest.mark.parametrize("fecha", ["hoy", "mañana", "ayer", "fecha de suscripcion hoy", "xx", "pronto"])
def test_una_fecha_que_no_es_una_fecha_es_error(fecha):
    assert _por_campo({**DATOS, "fecha": fecha})["fecha"].nivel == "error"


@pytest.mark.parametrize("fecha", ["1 de octubre de 2026", "01/10/2026", "1-10-2026", "primero de octubre de 2026",
                                   "15 de MARZO de 2027"])
def test_las_fechas_bien_escritas_pasan(fecha):
    assert "fecha" not in _por_campo({**DATOS, "fecha": fecha})


def test_una_fecha_sin_anio_solo_avisa():
    p = _por_campo({**DATOS, "fecha": "1 de octubre"})["fecha"]
    assert p.nivel == "aviso"


@pytest.mark.parametrize("lugar", ["SANTA CRUZ", "Santa Cruz de la Sierra", "La Paz", "LA PAZ", "Cochabamba",
                                   "Sucre, Bolivia"])
def test_los_lugares_bien_escritos_pasan_aunque_esten_en_mayusculas(lugar):
    assert "lugar" not in _por_campo({**DATOS, "lugar": lugar})


@pytest.mark.parametrize("lugar,sugerencia", [("SCZ", "Santa Cruz de la Sierra"), ("Lpz", None), ("cbba", None),
                                              ("en SCZ", "Santa Cruz de la Sierra")])
def test_una_sigla_como_lugar_se_senala(lugar, sugerencia):
    problemas = _por_campo({**DATOS, "lugar": lugar})
    if lugar == "Lpz":          # «Lpz» no está toda en mayúsculas: no se trata como sigla
        assert "lugar" not in problemas
        return
    if lugar == "cbba":         # todo en minúsculas: tampoco es una sigla en mayúsculas
        assert "lugar" not in problemas
        return
    assert "sigla" in problemas["lugar"].mensaje
    assert sugerencia is None or sugerencia in problemas["lugar"].mensaje


def test_el_documento_de_identidad_necesita_numeros():
    assert _por_campo({**DATOS, "prestamista_ci": "sin carnet"})["prestamista_ci"].nivel == "error"
    assert _por_campo({**DATOS, "prestamista_ci": "12"})["prestamista_ci"].nivel == "error"
    assert "prestamista_ci" not in _por_campo({**DATOS, "prestamista_ci": "4587963 SC"})
    assert "prestamista_ci" not in _por_campo({**DATOS, "prestamista_ci": "1234567-1L"})


def test_el_nombre_pide_nombre_y_apellido():
    assert "apellido" in _por_campo({**DATOS, "prestatario_nombre": "María"})["prestatario_nombre"].mensaje
    assert "números" in _por_campo({**DATOS, "prestatario_nombre": "María 2"})["prestatario_nombre"].mensaje
    assert "prestatario_nombre" not in _por_campo({**DATOS, "prestatario_nombre": "María Fernanda López"})


def test_el_monto_necesita_numero_y_avisa_si_falta_la_moneda():
    assert _por_campo({**DATOS, "monto": "mucho"})["monto"].nivel == "error"
    assert _por_campo({**DATOS, "monto": "25.000"})["monto"].nivel == "aviso"
    for bueno in ("Bs 25.000", "25.000 bolivianos", "USD 1.000", "veinte mil bolivianos", "$us 500"):
        assert "monto" not in _por_campo({**DATOS, "monto": bueno}), bueno


def test_el_plazo_pide_un_numero_o_una_unidad():
    assert _por_campo({**DATOS, "plazo_devolucion": "pronto"})["plazo_devolucion"].nivel == "error"
    for bueno in ("12 meses", "un año", "hasta el 30 de septiembre de 2027", "seis meses"):
        assert "plazo_devolucion" not in _por_campo({**DATOS, "plazo_devolucion": bueno}), bueno


def test_un_campo_vacio_no_es_un_problema():
    # Lo que se deja vacío queda marcado como pendiente en el borrador; no es un error del usuario.
    assert revision_datos.revisar_datos(PRESTAMO, {}) == []


# --- El controlador: se dice ANTES de gastar minutos de IA, y con estructura --------------------

def test_generar_con_datos_que_no_sirven_falla_antes_de_llamar_a_la_ia(monkeypatch):
    def no_debe_llamarse(*a, **k):
        raise AssertionError("no debía llamar a la IA con datos inválidos")
    monkeypatch.setattr(controlador, "generar_borrador", no_debe_llamarse)
    with pytest.raises(controlador.DatosInvalidosError) as error:
        controlador.generar(None, uuid4(), TipoDocumento.PRESTAMO, {**DATOS, "fecha": "hoy", "lugar": "SCZ"})
    assert [c.clave for c in error.value.campos] == ["fecha"]      # la sigla es un aviso: no bloquea
    assert "Fecha de suscripción" in str(error.value)


def test_un_aviso_no_impide_generar(monkeypatch):
    llamado = {}
    monkeypatch.setattr(controlador, "generar_borrador",
                        lambda *a, **k: llamado.setdefault("si", BorradorIA(disponible=False, motivo="x")))
    with pytest.raises(controlador.GeneracionNoDisponibleError):
        controlador.generar(None, uuid4(), TipoDocumento.PRESTAMO, {**DATOS, "fecha": "1 de octubre"})
    assert llamado  # la fecha sin año es solo un aviso: se intentó generar


def test_un_borrador_rechazado_explica_que_paso_y_que_campos_mirar(monkeypatch):
    rechazado = BorradorIA(disponible=False, motivo="genérico", motivo_codigo="dato_no_proporcionado",
                           detalle_rechazo="Ricardo, Oruro", clausula_rechazada="OBJETO Y MONTO")
    monkeypatch.setattr(controlador, "generar_borrador", lambda *a, **k: rechazado)
    with pytest.raises(controlador.BorradorNoValidadoError) as error:
        controlador.generar(None, uuid4(), TipoDocumento.PRESTAMO, {**DATOS, "fecha": "1 de octubre"})
    mensaje = str(error.value)
    assert "Ricardo, Oruro" in mensaje and "OBJETO Y MONTO" in mensaje and "no permite inventar" in mensaje
    assert [c.clave for c in error.value.campos] == ["fecha"]      # el aviso: fecha sin año
    assert error.value.campos[0].nivel == "aviso"


def test_si_la_ia_no_esta_disponible_sigue_siendo_ese_error(monkeypatch):
    monkeypatch.setattr(controlador, "generar_borrador",
                        lambda *a, **k: BorradorIA(disponible=False, motivo="El servicio local de IA no responde."))
    with pytest.raises(controlador.GeneracionNoDisponibleError):
        controlador.generar(None, uuid4(), TipoDocumento.PRESTAMO, DATOS)


def test_interpretar_agrega_los_campos_con_problemas(monkeypatch):
    monkeypatch.setattr(controlador, "interpretar", lambda *a, **k: InterpretacionResponse(
        tipo_documento=TipoDocumento.PRESTAMO, datos={**DATOS, "fecha": "hoy", "lugar": "lugaR DE SUSCRIPCION SCZ"}))
    monkeypatch.setattr(controlador, "get_settings", lambda: type("S", (), {"ia_enabled": True})())
    respuesta = controlador.interpretar_pedido("texto")
    assert {p.clave for p in respuesta.problemas} == {"lugar", "fecha"}
    assert respuesta.problemas[0].ejemplo


def test_las_plantillas_llevan_un_ejemplo_por_campo():
    for plantilla in plantillas.PLANTILLAS.values():
        assert all(c.ejemplo.startswith("Ej.:") for c in plantilla.campos), plantilla.tipo
    api = controlador.listar_plantillas()
    assert all(c.ejemplo for p in api for c in p.campos)
