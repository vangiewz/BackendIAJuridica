"""Compara ranking léxico y embedding concurrente sin guardar ni regenerar vectores."""
import argparse
import json
from pathlib import Path
from time import perf_counter
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.database import obtener_engine
from app.services.conocimiento.busqueda_lexica import buscar, buscar_candidatos
from app.services.conocimiento.busqueda_hibrida import buscar_hibrida
from app.services.conocimiento.expansion_consulta import expandir_consulta
from scripts.benchmark_pipeline import CASOS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="docs/benchmarks/retrieval.json")
    args = parser.parse_args()
    rows = []
    settings = get_settings()
    previous = settings.rag_parallel_embedding
    try:
        with Session(obtener_engine()) as db:
            for case in CASOS[:6]:
                ident, pregunta, _ = case
                texto, _ = expandir_consulta(pregunta)
                tick = perf_counter()
                _, old = buscar(db, texto, limite=settings.rag_candidate_k)
                old_ms = (perf_counter()-tick)*1000
                tick = perf_counter()
                new = buscar_candidatos(db, texto, limite=settings.rag_candidate_k)
                new_ms = (perf_counter()-tick)*1000
                row = {"id": ident, "lexical_old_ms": old_ms, "lexical_new_ms": new_ms,
                    "same_ranking": [(r.Norma.id, r.relevancia) for r in old] ==
                                    [(r.Norma.id, r.relevancia) for r in new]}
                variants = []
                # Alternar el orden reduce el sesgo del primer embedding/conexión.
                for parallel in ([False, True] if len(rows) % 2 == 0 else [True, False]):
                    settings.rag_parallel_embedding = parallel
                    tick = perf_counter()
                    result = buscar_hibrida(db, pregunta)
                    row["parallel_ms" if parallel else "serial_ms"] = (perf_counter()-tick)*1000
                    variants.append([str(r.Norma.id) for r in result.resultados])
                row["same_sources"] = variants[0] == variants[1]
                rows.append(row)
                print(json.dumps(row), flush=True)
        Path(args.output).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    finally:
        settings.rag_parallel_embedding = previous


if __name__ == "__main__":
    main()
