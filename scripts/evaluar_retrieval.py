"""Evaluación de recuperación sobre normas reales; no fabrica gold jurídico."""
import argparse
import json
import unicodedata
from pathlib import Path
from time import perf_counter
from sqlalchemy.orm import Session
from app.core.database import obtener_engine
from app.services.conocimiento.busqueda_lexica import buscar
from app.services.conocimiento.busqueda_hibrida import buscar_semantica, buscar_hibrida


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFD', value.lower()) if unicodedata.category(c) != 'Mn')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salida", default="docs/evaluacion_retrieval.json")
    args = parser.parse_args()
    cases = json.loads(Path("tests/evaluacion_ia/casos.json").read_text(encoding="utf-8"))
    report = {"k": 5, "recall_at_k": None,
              "nota": "Sin gold jurídico humano. Coincidencia conceptual en texto/metadatos es un proxy, no relevancia legal validada.", "casos": []}
    with Session(obtener_engine()) as db:
        for case in cases[:6]:
            row = {"id": case["id"], "pregunta": case["pregunta"], "metodos": {}}
            for method in ("lexica", "semantica", "hibrida"):
                tick = perf_counter()
                if method == "lexica":
                    _, results = buscar(db, case["pregunta"], limite=5)
                elif method == "semantica":
                    results = buscar_semantica(db, case["pregunta"], limite=5)
                else:
                    retrieval = buscar_hibrida(db, case["pregunta"], limite=5)
                    if retrieval.modo != "hibrida":
                        raise RuntimeError("La evaluación requiere ambos canales disponibles")
                    results = retrieval.resultados
                latency = round((perf_counter()-tick)*1000, 2)
                articles = []
                for item in results:
                    n = item.Norma
                    content = normalize(' '.join(str(v or '') for v in [n.epigrafe,n.texto,n.libro,n.titulo,n.capitulo]))
                    articles.append({"id": str(n.id), "codigo": n.codigo, "articulo": n.numero_articulo,
                        "epigrafe": n.epigrafe, "version": n.version, "area": n.area_juridica,
                        "score": float(item.relevancia),
                        "coincidencia_conceptual": any(normalize(c) in content for c in case["conceptos"])})
                row["metodos"][method] = {"latencia_ms": latency, "articulos": articles,
                    "hit_conceptual_at_5": any(a["coincidencia_conceptual"] for a in articles)}
            report["casos"].append(row)
            print(json.dumps({"caso":case["id"], "hibrida_ms":row["metodos"]["hibrida"]["latencia_ms"]}), flush=True)
    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    Path(args.salida).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({method:sum(c["metodos"][method]["hit_conceptual_at_5"] for c in report["casos"])
                      for method in ("lexica","semantica","hibrida")}))


if __name__ == "__main__":
    main()
