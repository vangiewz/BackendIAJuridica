"""Evaluación extremo a extremo del RAG sobre normas reales.

Mide propiedades verificables del sistema (grounding, citas, abstención, tiempos).
No mide corrección jurídica: no existe un conjunto de respuestas legales validadas
por un profesional, y este informe no debe leerse como si existiera.
"""
import argparse
import json
from pathlib import Path
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import obtener_engine
from app.models.conocimiento.norma import Norma
from app.services.ia.rag import responder
from app.services.ia.validacion import normalizar

CASOS = Path("tests/evaluacion_ia/casos.json")


def evaluar_caso(db, caso):
    inicio = perf_counter()
    respuesta = responder(db, caso["pregunta"])
    total_ms = round((perf_counter() - inicio) * 1000, 2)
    traza = respuesta.trazabilidad
    fuentes = {str(f.id): f for f in respuesta.fuentes}

    # Grounding: cada fundamento debe apuntar a una norma que el retrieval entregó,
    # que siga activa en la base y cuya cita esté literalmente en su texto.
    citas = []
    for fundamento in respuesta.analisis:
        norma_id = str(fundamento.norma_id)
        norma = db.get(Norma, fundamento.norma_id)
        citas.append({
            "fuente_en_retrieval": norma_id in fuentes,
            "norma_existe_y_activa": bool(norma and norma.activa),
            "cita_literal": bool(norma and normalizar(fundamento.cita_textual) in normalizar(norma.texto)),
            "articulo": norma.numero_articulo if norma else None,
        })

    abstuvo = respuesta.estado != "fundamentada"
    return {
        "id": caso["id"],
        "pregunta": caso["pregunta"],
        "estado": respuesta.estado,
        "area_detectada": respuesta.area_juridica,
        "area_esperada": caso["area"],
        "debia_abstenerse": caso["abstencion"],
        "se_abstuvo": abstuvo,
        "abstencion_correcta": abstuvo == caso["abstencion"],
        "fuentes_recuperadas": len(respuesta.fuentes),
        "fundamentos": len(respuesta.analisis),
        "citas": citas,
        "contexto_hechos": len(respuesta.contexto.hechos),
        "contexto_actores": len(respuesta.contexto.actores),
        "tiempos_ms": {
            "contexto": traza.get("contexto_ms"),
            "lexica": traza.get("lexica"),
            "semantica": traza.get("semantica"),
            "retrieval": traza.get("retrieval"),
            "llm": traza.get("llm_ms"),
            "total": total_ms,
        },
        "intentos_validacion": traza.get("intentos_validacion"),
        "validacion_motivo": traza.get("validacion_motivo"),
    }


def resumir(filas):
    citas = [c for fila in filas for c in fila["citas"]]
    tiempos = lambda clave: [f["tiempos_ms"][clave] for f in filas if f["tiempos_ms"].get(clave)]
    promedio = lambda valores: round(sum(valores) / len(valores), 1) if valores else None
    return {
        "casos": len(filas),
        # El JSON estructurado es condición para llegar hasta aquí: una salida no
        # parseable habría terminado en abstención por validación.
        "estructura_json_valida": sum(1 for f in filas if f["estado"] != "error_validacion"),
        "abstencion_correcta": f"{sum(f['abstencion_correcta'] for f in filas)}/{len(filas)}",
        "fundamentos_totales": len(citas),
        "grounding_fuente_en_retrieval": f"{sum(c['fuente_en_retrieval'] for c in citas)}/{len(citas)}",
        "citas_con_norma_activa": f"{sum(c['norma_existe_y_activa'] for c in citas)}/{len(citas)}",
        "citas_literales": f"{sum(c['cita_literal'] for c in citas)}/{len(citas)}",
        "latencia_media_ms": {
            "contexto": promedio(tiempos("contexto")), "retrieval": promedio(tiempos("retrieval")),
            "llm": promedio(tiempos("llm")), "total": promedio(tiempos("total")),
        },
        "latencia_maxima_total_ms": max(tiempos("total")) if tiempos("total") else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salida", default="docs/evaluacion_rag.json")
    argumentos = parser.parse_args()
    casos = json.loads(CASOS.read_text(encoding="utf-8"))
    filas = []
    with Session(obtener_engine()) as db:
        for caso in casos:
            fila = evaluar_caso(db, caso)
            filas.append(fila)
            print(json.dumps({"caso": fila["id"], "estado": fila["estado"],
                              "abstencion_ok": fila["abstencion_correcta"],
                              "total_ms": fila["tiempos_ms"]["total"]}, ensure_ascii=False), flush=True)
    informe = {
        "nota": ("Mide propiedades verificables del sistema, no corrección jurídica. "
                 "No hay respuestas legales validadas por un profesional."),
        "resumen": resumir(filas), "casos": filas,
    }
    salida = Path(argumentos.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(informe["resumen"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
