"""python -m scripts.diagnosticar_ia [--medir-embedding]. No modifica la base."""
import argparse
import json
from app.services.ia.diagnostico import diagnosticar


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--medir-embedding", action="store_true")
    args = parser.parse_args()
    result = diagnosticar(medir_embedding=args.medir_embedding)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if (result["ollama_disponible"] and result["modelo_principal_disponible"]
                 and result["embedding_disponible"] and result["base"]["estado"] == "ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
