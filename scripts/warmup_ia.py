"""Carga modelos locales para una demo. No consulta ni escribe en la base de datos."""
import json
from time import perf_counter
from app.core.config import get_settings
from app.services.ia.ollama_client import OllamaClient, IAError


def main():
    settings = get_settings()
    client = OllamaClient(settings)
    tick = perf_counter()
    try:
        modelos = client.modelos()
        if any(m not in modelos for m in (settings.ollama_model, settings.embedding_model)):
            raise IAError("Falta un modelo local configurado.")
        client.comprobar_modelo(settings.ollama_model, "completion")
        # Embedding técnico solo en memoria; nunca regenerar los vectores persistidos.
        vector = client.embeddings(["Comprobación técnica de disponibilidad"])[0]
        if len(vector) != 1024:
            raise IAError("El embedding no tiene las 1024 dimensiones esperadas.")
        # messages=[] es la operación documentada de carga, sin generar una consulta.
        result = client._request("POST", "/api/chat", {
            "model": settings.ollama_model, "messages": [], "stream": False,
            "keep_alive": settings.ollama_keep_alive,
            "options": {"num_ctx": settings.ollama_num_ctx},
        })
        print(json.dumps({"ok": True, "model": settings.ollama_model,
            "keep_alive": settings.ollama_keep_alive, "embedding_dimension": len(vector),
            "load_ms": result.get("load_duration", 0)/1e6,
            "total_ms": round((perf_counter()-tick)*1000, 2)}))
    except IAError as exc:
        print(json.dumps({"ok": False, "motivo": str(exc)}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
