"""HU-10/13/14/15: benchmark sintético local, sin guardar documentos."""
import argparse
import json
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
from types import SimpleNamespace
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.database import obtener_engine
from app.models.conocimiento.norma import Norma
from app.models.shared.enums import TipoDocumento
from app.services.contratos.motor_riesgos import analizar
from app.services.ia.contratos import analizar_contrato
from app.services.ia.explicacion import explicar_articulo
from app.services.ia.generacion import generar_borrador
from app.services.ia.ollama_client import OllamaClient

DATOS = {
    "arrendador_nombre": "Luis Mendoza Roca", "arrendador_ci": "4567890 SC",
    "arrendatario_nombre": "Ana Rojas Vaca", "arrendatario_ci": "9876543 SC",
    "lugar": "Santa Cruz de la Sierra", "fecha": "10 de marzo de 2026",
    "inmueble": "Departamento 3B, calle Independencia 45",
    "canon": "2500 bolivianos mensuales", "plazo": "12 meses",
}
PRESTAMO = """CONTRATO DE PRÉSTAMO
PRIMERA.- El prestamista entrega al prestatario 10000 bolivianos en calidad de préstamo.
SEGUNDA.- El prestatario devolverá el monto en el plazo de seis meses.
TERCERA.- El interés mensual será del 5%.
CUARTA.- Las partes aceptan el contenido del contrato."""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model")
    args = parser.parse_args()
    if args.model:
        get_settings().ollama_model = args.model
    report = {"model": get_settings().ollama_model, "cases": []}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    original = OllamaClient._request
    calls = []

    def measured(client, method, path, payload=None, timeout=None):
        tick = perf_counter()
        data = original(client, method, path, payload, timeout)
        if path == "/api/chat":
            calls.append({"ms": (perf_counter()-tick)*1000, **{k: data.get(k) for k in
                ("load_duration", "prompt_eval_duration", "eval_duration", "prompt_eval_count", "eval_count", "done_reason")}})
        return data

    def run(ident, fn):
        calls.clear()
        tick = perf_counter()
        with patch.object(OllamaClient, "_request", measured):
            result = fn()
        row = {"id": ident, "total_ms": (perf_counter()-tick)*1000,
               "disponible": result.disponible, "trace": result.trazabilidad,
               "calls": list(calls)}
        if hasattr(result, "clausulas"):
            row["clausulas"] = len(result.clausulas)
            row["datos_conservados"] = all(v in (result.contenido or "") for v in DATOS.values()) if ident == "generacion" else None
            row["faltantes"] = result.campos_faltantes
        report["cases"].append(row)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k: row[k] for k in ("id", "total_ms", "disponible")}), flush=True)
        return result

    with Session(obtener_engine()) as db:
        norma = db.scalar(select(Norma).where(Norma.activa.is_(True), Norma.numero_articulo == 984))
        run("explicacion", lambda: explicar_articulo(norma))
        motor = analizar(PRESTAMO, TipoDocumento.PRESTAMO)
        riesgos = [SimpleNamespace(codigo_regla=r.codigo, descripcion=r.titulo,
            severidad=r.severidad, articulos=r.articulos, evidencia=r.evidencia) for r in motor.riesgos]
        run("contrato_prestamo", lambda: analizar_contrato(db, TipoDocumento.PRESTAMO, PRESTAMO,
            [asdict(c) for c in motor.clausulas], [asdict(h) for h in motor.hallazgos], riesgos))
        borrador = run("generacion", lambda: generar_borrador(db, TipoDocumento.ARRENDAMIENTO, DATOS))
        if borrador.disponible:
            run("revision", lambda: generar_borrador(db, TipoDocumento.ARRENDAMIENTO, DATOS,
                "Cambiar el plazo de 12 meses a 24 meses", borrador.contenido))


if __name__ == "__main__":
    main()
