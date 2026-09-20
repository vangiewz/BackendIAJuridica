"""Pruebas E2E HTTP con datos sintéticos. Añade registros de prueba, nunca borra datos."""
import json
import argparse
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.main import app
from app.core.config import get_settings
from app.core.database import obtener_engine
from app.models.conocimiento.norma import Norma
from scripts.benchmark_pipeline import CASOS
from scripts.benchmark_funciones import DATOS, PRESTAMO


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persistence-only", action="store_true")
    parser.add_argument("--output", default="docs/benchmarks/e2e.json")
    args = parser.parse_args()
    settings = get_settings()
    output = Path(args.output)
    results = []
    client = TestClient(app)
    cred = {"email": f"rendimiento_{uuid4()}@ejemplo.com", "password": "PruebaSintetica123!"}
    assert client.post("/api/v1/auth/registro", json={**cred, "nombre": "Prueba rendimiento"}).status_code == 201
    login = client.post("/api/v1/auth/login", json=cred)
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}

    def run(ident, fn, check):
        commit_ms = []
        original_commit = Session.commit

        def measured_commit(db):
            tick = perf_counter()
            try:
                return original_commit(db)
            finally:
                commit_ms.append((perf_counter()-tick)*1000)

        tick = perf_counter()
        with patch.object(Session, "commit", measured_commit):
            res = fn()
        data = res.json()
        row = {"id": ident, "status": res.status_code, "ms": (perf_counter()-tick)*1000,
               "ok": bool(res.status_code < 400 and check(data)),
               "commit_ms": sum(commit_ms), "commits": len(commit_ms)}
        if isinstance(data, dict) and isinstance(data.get("respuesta"), dict):
            row["metrics"] = data["respuesta"].get("trazabilidad", {}).get("metricas", {})
        results.append(row)
        output.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps({k: row[k] for k in ("id", "status", "ms", "ok")}), flush=True)
        return data

    first = None
    for ident, pregunta, abstener in [CASOS[i] for i in ((0,) if args.persistence_only else (0, 1, 3, 8, 9, 6, 7))]:
        data = run(ident, lambda: client.post("/api/v1/consultas", json={"texto": pregunta}, headers=headers),
            lambda d: (d["respuesta"]["estado"] != "fundamentada") == abstener)
        first = first or data
    if args.persistence_only:
        run("historial", lambda: client.get(f"/api/v1/consultas/{first['id']}", headers=headers),
            lambda d: d["respuesta"]["conclusion"] == first["respuesta"]["conclusion"])
        return
    with Session(obtener_engine()) as db:
        codigo = db.scalar(select(Norma.codigo).where(Norma.activa.is_(True), Norma.numero_articulo == 984))
    for ident in ("explicacion", "explicacion_cache"):
        run(ident, lambda: client.get(f"/api/v1/normativa/articulos/{codigo}/984/explicacion", headers=headers),
            lambda d: d["disponible"] and bool(d["texto_original"]))
    upload = client.post("/api/v1/documentos", headers=headers,
        files={"archivo": ("prestamo_benchmark.txt", PRESTAMO.encode("utf-8"), "text/plain")})
    assert upload.status_code == 201
    run("prestamo", lambda: client.post(f"/api/v1/documentos/{upload.json()['id']}/analisis", headers=headers),
        lambda d: bool(d["resumen"]) and d["reglas_evaluadas"] > 0)
    run("generacion", lambda: client.post("/api/v1/documentos-generados", headers=headers,
        json={"tipo_documento": "arrendamiento", "datos": DATOS}),
        lambda d: all(v in d["contenido"] for v in DATOS.values()) and
                  "[FALTA: Destino o uso del inmueble]" in d["contenido"])
    run("historial", lambda: client.get(f"/api/v1/consultas/{first['id']}", headers=headers),
        lambda d: d["respuesta"]["conclusion"] == first["respuesta"]["conclusion"])
    original_url = settings.ollama_url
    try:
        # Rechazo real de conexión en loopback; no interrumpe el servidor del usuario.
        settings.ollama_url = "http://127.0.0.1:1"
        run("sin_ollama_normativa", lambda: client.get("/api/v1/normativa/buscar", params={"q": "arrendamiento"}),
            lambda d: d["total"] > 0)
        run("sin_ollama_historial", lambda: client.get("/api/v1/consultas/historial", headers=headers),
            lambda d: d["total"] > 0)
        run("sin_ollama_consulta", lambda: client.post("/api/v1/consultas", headers=headers,
            json={"texto": CASOS[0][1]}),
            lambda d: d["estado"] == "completado" and d["respuesta"]["estado"] == "no_disponible" and bool(d["fuentes"]))
    finally:
        settings.ollama_url = original_url
    if not all(r["ok"] for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
