"""Comprueba que este equipo puede ejecutar el backend. No genera texto ni escribe datos.

    python -m scripts.verificar_entorno

Sale con código 1 si falla alguna comprobación obligatoria (marcadas FALLA).
Las opcionales (marcadas AVISO) no cambian el código de salida.
"""
import importlib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MODULOS = ["fastapi", "uvicorn", "pydantic_settings", "sqlalchemy", "psycopg", "pgvector",
           "alembic", "jwt", "bcrypt", "httpx", "pypdf", "docx", "openpyxl", "pptx",
           "reportlab", "multipart", "email_validator"]

fallas = 0


def ok(texto):
    print(f"  OK     {texto}")


def aviso(texto):
    print(f"  AVISO  {texto}")


def falla(texto):
    global fallas
    fallas += 1
    print(f"  FALLA  {texto}")


def python_y_paquetes():
    print("Python y paquetes")
    version = sys.version_info
    (ok if version[:2] == (3, 13) else aviso)(
        f"Python {version.major}.{version.minor}.{version.micro} (probado con 3.13)")
    faltan = []
    for nombre in MODULOS:
        try:
            importlib.import_module(nombre)
        except ImportError:
            faltan.append(nombre)
    if faltan:
        falla("faltan paquetes: " + ", ".join(faltan) + "  ->  pip install -r requirements.txt")
    else:
        ok(f"{len(MODULOS)} paquetes importables")


def configuracion():
    print("Configuracion (.env)")
    if not (RAIZ / ".env").exists():
        falla("no existe .env  ->  copiar .env.example como .env y completarlo")
    try:
        from app.core.config import get_settings
        ajustes = get_settings()
    except Exception as exc:  # validacion de pydantic: el mensaje explica el campo
        falla(f"configuracion invalida: {exc}")
        return None
    ok("el backend importa y la configuracion es valida")
    (ok if ajustes.ia_pipeline == "simple" else aviso)(
        f"IA_PIPELINE={ajustes.ia_pipeline} (recomendado: simple)")
    if not ajustes.database_url or "usuario:password@" in ajustes.database_url:
        falla("DATABASE_URL vacia o sigue con el valor de ejemplo")
    else:
        ok("DATABASE_URL definida")
    ok(f"modelo {ajustes.ollama_model} | embeddings {ajustes.embedding_model} | num_ctx {ajustes.ollama_num_ctx}")
    return ajustes


def ollama(ajustes):
    print("Ollama")
    from app.services.ia.ollama_client import IAError, OllamaClient
    try:
        instalados = OllamaClient(ajustes).modelos()
    except IAError:
        falla(f"no responde en {ajustes.ollama_url}  ->  abrir Ollama (ollama serve) o instalarlo")
        return
    ok(f"responde en {ajustes.ollama_url}")
    for modelo in (ajustes.ollama_model, ajustes.embedding_model):
        if modelo in instalados:
            ok(f"modelo instalado: {modelo}")
        else:
            falla(f"falta el modelo {modelo}  ->  ollama pull {modelo}")


def base_de_datos():
    print("Base de datos")
    try:
        from app.core.database import verificar_conexion
        estado = verificar_conexion()
    except Exception as exc:
        falla(f"no se pudo consultar la base: {type(exc).__name__}")
        return
    (ok if estado == "ok" else falla)(f"conexion: {estado}")


def main():
    sys.path.insert(0, str(RAIZ))
    python_y_paquetes()
    ajustes = configuracion()
    if ajustes is not None:
        ollama(ajustes)
        if ajustes.database_url and "usuario:password@" not in ajustes.database_url:
            base_de_datos()
    print()
    if fallas:
        print(f"{fallas} comprobacion(es) obligatoria(s) fallaron.")
        raise SystemExit(1)
    print("Entorno listo. Siguiente paso: python -m scripts.warmup_ia")


if __name__ == "__main__":
    main()
