"""Indexación local reanudable. python -m scripts.generar_embeddings [--force]."""
import argparse
import json
import time
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session, defer

from app.core.database import obtener_engine
from app.models.shared import registro  # registra FKs
from app.models.conocimiento.norma import Norma
from app.models.conocimiento.embedding import NormaEmbedding
from app.services.ia.embeddings import documento_norma, huella_documento, texto_para_embedding
from app.services.ia.ollama_client import OllamaClient


def indexar(force=False, limite=None) -> dict:
    started = time.perf_counter()
    engine = obtener_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL no configurada")
    client = OllamaClient()
    model = client.settings.embedding_model
    digest = client.modelos().get(model)
    if not digest:
        raise RuntimeError("Modelo de embeddings no instalado")
    dimensions = len(client.embeddings(["prueba técnica de dimensión"])[0])
    if dimensions != 1024:
        raise RuntimeError("Dimensión incompatible con vector(1024); no se guardaron vectores")
    created = skipped = errors = 0
    embedding_seconds = 0.0
    with Session(engine, expire_on_commit=False) as db:
        rows = db.execute(select(Norma, NormaEmbedding).options(defer(NormaEmbedding.vector)).outerjoin(
            NormaEmbedding, NormaEmbedding.norma_id == Norma.id).where(Norma.activa.is_(True))
            .order_by(Norma.codigo, Norma.numero_articulo)).all()
        ids = [norma.id for norma, _ in rows]
        pending = []
        for norma, old in (rows[:limite] if limite else rows):
            fingerprint = huella_documento(documento_norma(norma))
            if (not force and old and old.contenido_hash == fingerprint
                    and old.modelo_digest == digest and old.modelo == model
                    and old.dimension == dimensions):
                skipped += 1
            else:
                pending.append((norma, old, fingerprint))
        db.commit()  # no mantener una transacción abierta durante toda la inferencia
        for offset in range(0, len(pending), 8):
            batch = pending[offset:offset+8]
            try:
                tick = time.perf_counter()
                vectors = client.embeddings([texto_para_embedding(n) for n, _, _ in batch])
                embedding_seconds += time.perf_counter() - tick
                for (norma, old, fingerprint), vector in zip(batch, vectors):
                    if len(vector) != dimensions:
                        raise ValueError("Dimensión cambió durante indexación")
                    row = old or NormaEmbedding(norma_id=norma.id)
                    row.modelo, row.modelo_digest = model, digest
                    row.contenido_hash, row.dimension, row.vector = fingerprint, dimensions, vector
                    row.creado_en = datetime.now(timezone.utc)
                    db.add(row)
                db.commit()  # checkpoint atómico por lote, reanudable
                created += len(batch)
                print(json.dumps({"procesados": offset+len(batch), "total": len(pending),
                                  "generados": created, "errores": errors}), flush=True)
            except Exception as exc:
                db.rollback()
                errors += len(batch)
                print(json.dumps({"norma_ids": [str(n.id) for n, _, _ in batch],
                                  "error": type(exc).__name__}), flush=True)
        # Cuenta cobertura actual por hash, no solo filas potencialmente desactualizadas.
        valid = 0
        for norma, emb in db.execute(select(Norma, NormaEmbedding).options(defer(NormaEmbedding.vector)).outerjoin(
                NormaEmbedding, NormaEmbedding.norma_id == Norma.id).where(Norma.activa.is_(True))):
            if (emb and emb.modelo == model and emb.modelo_digest == digest
                    and emb.dimension == dimensions
                    and emb.contenido_hash == huella_documento(documento_norma(norma))):
                valid += 1
    return {"activas": len(ids), "vectorizadas": valid, "faltantes": len(ids)-valid,
            "generados": created, "omitidos": skipped, "errores": errors,
            "dimension": dimensions, "tiempo_total_s": round(time.perf_counter()-started, 3),
            "embedding_promedio_s": round(embedding_seconds/created, 3) if created else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limite", type=int, default=None, help="Lote inicial de verificación")
    args = parser.parse_args()
    if args.limite is not None and args.limite < 1:
        parser.error("--limite debe ser positivo")
    try:
        result = indexar(args.force, args.limite)
        print(json.dumps(result, indent=2), flush=True)
        return int(result["errores"] > 0 or (result["faltantes"] > 0 and args.limite is None))
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "mensaje": "No se pudo iniciar la indexación; revise diagnóstico IA"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
