import json
from uuid import uuid4
import httpx
from app.core.config import Settings
from app.models.ia.esquemas import FuenteIA, ExplicacionArticuloIA
from app.services.ia.cache_publica import CachePublica
from app.services.ia.ollama_client import OllamaClient
from app.services.ia.rag import generar_con_fuentes


def fuente():
    return FuenteIA(id=uuid4(), codigo="Codigo Civil", numero_articulo=701, articulo="701",
        epigrafe=None, texto="El arrendatario debe pagar el canon en los plazos convenidos.",
        version=1, estado_vigencia="sin_verificar", fuente_nombre="fixture", fuente_url="",
        contenido_hash="fixture")


def cliente(contexto, cita=None):
    llamadas = []

    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion"]})
        llamadas.append(json.loads(request.content))
        salida = {"resumen": "El inquilino no paga.", "analisis": [{
            "cita_id": cita or "F1C1",
            "explicacion": "La obligación de pago debe contrastarse con lo acordado."}],
            "suficiente": True, "conclusion": "Revise las condiciones acordadas.",
            "limitaciones": [], "contexto": contexto}
        return httpx.Response(200, json={"done": True, "message": {"content": json.dumps(salida)}})

    return OllamaClient(Settings(_env_file=None), httpx.MockTransport(handler)), llamadas


def test_una_llamada_conserva_contexto_y_grounding():
    client, llamadas = cliente({"hechos": ["Mi inquilino no paga"], "actores": [
        {"rol": "arrendatario", "evidencia": "inquilino", "nombre": None}]})
    result = generar_con_fuentes("Mi inquilino no paga", [fuente()], client=client, integrar_contexto=True)
    assert len(llamadas) == 1
    assert result.estado == "fundamentada"
    assert result.contexto.actores[0].rol == "arrendatario"
    # El presupuesto de salida ya no se fija en el mínimo que bastaba para ir rápido: una
    # consulta con varios fundamentos necesita espacio para desarrollarlos. Lo que sigue
    # importando es que la respuesta salga de UNA llamada y con el modelo caliente.
    assert llamadas[0]["options"]["num_predict"] >= 2400
    assert llamadas[0]["keep_alive"] == "30m"


def test_contexto_inventado_no_se_publica():
    client, llamadas = cliente({"hechos": ["El deudor se llama Pedro"]})
    result = generar_con_fuentes("Mi inquilino no paga", [fuente()], client=client, integrar_contexto=True)
    assert result.estado == "fundamentada"
    assert not result.contexto.hechos
    # La traza cuenta cada descarte: el hecho inventado se pierde solo a sí mismo.
    assert result.trazabilidad["contexto_descartes"] == {"hecho_no_literal": 1}


def test_lo_literal_sobrevive_al_descarte_de_un_hecho_inventado():
    client, llamadas = cliente({
        "hechos": ["Mi inquilino no paga", "El deudor se llama Pedro"],
        "actores": [{"rol": "arrendatario", "evidencia": "inquilino", "nombre": None}]})
    result = generar_con_fuentes("Mi inquilino no paga", [fuente()], client=client, integrar_contexto=True)
    assert result.contexto.hechos == ["Mi inquilino no paga"]
    assert [a.rol for a in result.contexto.actores] == ["arrendatario"]
    assert result.trazabilidad["contexto_descartes"] == {"hecho_no_literal": 1}


def test_cita_inventada_sigue_reintentando_y_se_rechaza():
    client, llamadas = cliente({}, "F9999C1")
    result = generar_con_fuentes("Mi inquilino no paga", [fuente()], client=client, integrar_contexto=True)
    assert len(llamadas) == 2
    assert result.estado == "error_validacion"
    assert result.analisis == []
    assert len(result.fuentes) == 1


def test_fragmentos_reconstruyen_el_original_y_cita_sale_del_corpus():
    from app.services.ia.fragmentos import fragmentar
    from app.services.ia.prompts import construir_prompt
    source = fuente()
    source.texto = "I. Texto íntegro; con signos,\nacentos y espacios. " * 35
    partes = fragmentar(source.texto)
    assert "".join(partes) == source.texto
    assert all(12 <= len(p) <= 600 for p in partes)
    mensajes, usadas = construir_prompt("Consulta", [source], citas_identificadas=True)
    body = json.loads(mensajes[1]["content"])
    assert "".join(f["texto"] for f in body["FUENTES"][0]["fragmentos"]) == source.texto
    assert usadas == [source]


def test_cache_publica_copia_versiona_y_respeta_limites(monkeypatch):
    from app.services.ia import cache_publica
    clock = [0]
    monkeypatch.setattr(cache_publica, "monotonic", lambda: clock[0])
    cache = CachePublica()
    value = ExplicacionArticuloIA(disponible=True, articulo="1", texto_original="Texto", explicacion="Explicación")
    cache.guardar(("fuente-v1", "modelo-a", "prompt-1"), value, 1)
    assert cache.obtener(("fuente-v2", "modelo-a", "prompt-1"), 10, 1) is None
    assert cache.obtener(("fuente-v1", "modelo-b", "prompt-1"), 10, 1) is None
    assert cache.obtener(("fuente-v1", "modelo-a", "prompt-2"), 10, 1) is None
    hit = cache.obtener(("fuente-v1", "modelo-a", "prompt-1"), 10, 1)
    hit.explicacion = "Alterado"
    assert cache.obtener(("fuente-v1", "modelo-a", "prompt-1"), 10, 1).explicacion == "Explicación"
    assert cache.obtener(("fuente-v1", "modelo-a", "prompt-1"), 10, 0) is None
    clock[0] = 11
    assert cache.obtener(("fuente-v1", "modelo-a", "prompt-1"), 10, 1) is None
