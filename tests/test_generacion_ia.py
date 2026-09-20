"""HU-14 y HU-15: el borrador no puede contener datos que el usuario no dio."""
import json

import httpx
import pytest

from app.core.config import Settings
from app.models.shared.enums import TipoDocumento
from app.services.generacion import plantillas
from app.services.ia import generacion
from app.services.ia.ollama_client import OllamaClient, RespuestaInvalida

DATOS = {
    "arrendador_nombre": "Luis Mamani", "arrendador_ci": "4567890 SC",
    "arrendatario_nombre": "Ana Rojas", "arrendatario_ci": "9876543 SC",
    "lugar": "Santa Cruz", "fecha": "10 de marzo de 2026",
    "inmueble": "Departamento 3B", "canon": "2500 bolivianos", "plazo": "12 meses",
}


def cliente(clausulas, datos_actualizados=()):
    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion"]})
        if request.url.path == "/api/chat":
            return httpx.Response(200, json={"done": True, "message": {"content": json.dumps({
                "clausulas": clausulas, "datos_actualizados": list(datos_actualizados)},
                ensure_ascii=False)}})
        return httpx.Response(200, json={"models": []})
    return OllamaClient(Settings(_env_file=None), httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def sin_retrieval(monkeypatch):
    # La recuperación de normativa se prueba aparte; aquí importa la validación del borrador.
    monkeypatch.setattr(generacion, "buscar_hibrida",
                        lambda *a, **k: type("R", (), {"resultados": [], "tiempos_ms": {}})())


def generar(clausulas, datos=None, **extra):
    return generacion.generar_borrador(None, TipoDocumento.ARRENDAMIENTO,
        datos if datos is not None else DATOS, client=cliente(clausulas), **extra)


def test_el_borrador_usa_solo_los_datos_entregados():
    borrador = generar([{"titulo": "OBJETO", "texto": "Se arrienda el Departamento 3B por 12 meses."},
                        {"titulo": "CONFORMIDAD", "texto": "Las partes aceptan los términos."}])
    assert borrador.disponible
    assert "Luis Mamani" in borrador.contenido
    assert borrador.campos_faltantes == []
    assert borrador.trazabilidad["intentos_validacion"] == 1


def test_un_nombre_que_el_usuario_no_dio_se_rechaza():
    borrador = generar([{"titulo": "OBJETO",
                         "texto": "Se arrienda a Carlos Fernández el Departamento 3B."}])
    assert borrador.disponible is False
    assert borrador.trazabilidad["validacion_motivo"] == "dato_no_proporcionado"


def test_un_monto_que_el_usuario_no_dio_se_rechaza():
    borrador = generar([{"titulo": "CANON", "texto": "El canon mensual será de 7800 bolivianos."}])
    assert borrador.disponible is False
    assert borrador.trazabilidad["validacion_motivo"] == "cifra_fuera_de_fuentes"


def test_los_datos_obligatorios_ausentes_quedan_marcados():
    parciales = {k: v for k, v in DATOS.items() if k != "canon"}
    borrador = generar([{"titulo": "OBJETO", "texto": "Se arrienda el Departamento 3B."}], parciales)
    assert borrador.disponible
    assert "Canon de arrendamiento y moneda" in borrador.campos_faltantes
    assert plantillas.marcador("Canon de arrendamiento y moneda") in borrador.contenido


def test_la_instruccion_del_usuario_es_evidencia_valida():
    # "24 meses" no está en los datos originales pero sí en lo que el usuario pidió.
    borrador = generacion.generar_borrador(None, TipoDocumento.ARRENDAMIENTO, DATOS,
        instruccion="Cambiar el plazo de 12 meses a 24 meses", base="versión anterior",
        client=cliente([{"titulo": "PLAZO", "texto": "El plazo del arrendamiento es de 24 meses."}],
                       [{"clave": "plazo", "valor": "24 meses"}]))
    assert borrador.disponible
    # El encabezado se actualiza con la cláusula: el documento no puede contradecirse.
    assert "Plazo del contrato: 24 meses" in borrador.contenido


def test_un_dato_actualizado_que_nadie_pidio_se_rechaza():
    borrador = generacion.generar_borrador(None, TipoDocumento.ARRENDAMIENTO, DATOS,
        instruccion="Cambiar el plazo a 24 meses", base="versión anterior",
        client=cliente([{"titulo": "PLAZO", "texto": "El plazo es de 24 meses."}],
                       [{"clave": "arrendatario_nombre", "valor": "Pedro Suárez"}]))
    assert borrador.disponible is False
    assert borrador.trazabilidad["validacion_motivo"] == "dato_no_proporcionado"


def test_tipo_fuera_del_alcance():
    with pytest.raises(ValueError):
        plantillas.obtener(TipoDocumento.OTRO)


def test_los_datos_se_recuperan_del_documento_guardado():
    borrador = generar([{"titulo": "OBJETO", "texto": "Se arrienda el Departamento 3B."}])
    recuperados = plantillas.datos_desde_contenido(
        plantillas.obtener(TipoDocumento.ARRENDAMIENTO), borrador.contenido)
    assert recuperados["arrendatario_nombre"] == "Ana Rojas"
    assert recuperados["plazo"] == "12 meses"


def test_el_marcador_no_se_confunde_con_un_dato():
    parciales = {k: v for k, v in DATOS.items() if k != "canon"}
    borrador = generar([{"titulo": "OBJETO", "texto": "Se arrienda el Departamento 3B."}], parciales)
    recuperados = plantillas.datos_desde_contenido(
        plantillas.obtener(TipoDocumento.ARRENDAMIENTO), borrador.contenido)
    assert "canon" not in recuperados


def test_verificacion_directa_de_nombre_inventado():
    with pytest.raises(RespuestaInvalida) as error:
        generacion.verificar_sin_datos_inventados("Firma Rodrigo Céspedes", "evidencia sin ese nombre")
    assert error.value.motivo == "dato_no_proporcionado"


def test_un_marcador_de_campo_inexistente_se_rechaza():
    # `campos_faltantes` sale de leer los [FALTA: ...] del texto: si el modelo inventara
    # uno, aparecería como un dato que el sistema pide. Solo valen los de la plantilla.
    plantilla = plantillas.obtener(TipoDocumento.ARRENDAMIENTO)
    for inventado in ("[FALTA: nombre del garante solidario]",
                      "[FALTA: número de cuenta bancaria]",
                      "[FALTA: Cédula del testigo]"):
        with pytest.raises(RespuestaInvalida) as error:
            generacion.verificar_marcadores(f"El pago se hará en {inventado}.", plantilla)
        assert error.value.motivo == "campo_inexistente"


def test_los_marcadores_reales_de_la_plantilla_se_aceptan():
    plantilla = plantillas.obtener(TipoDocumento.ARRENDAMIENTO)
    for campo in plantilla.campos:
        generacion.verificar_marcadores(f"Consta en {plantillas.marcador(campo.etiqueta)}.",
                                        plantilla)
    # Sin marcadores tampoco hay nada que rechazar.
    generacion.verificar_marcadores("El plazo es de 12 meses.", plantilla)
