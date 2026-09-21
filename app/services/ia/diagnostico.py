"""Preflight explícito, de solo lectura. No se ejecuta al iniciar FastAPI."""
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import Settings, get_settings
from app.core.database import normalizar_url
from app.services.ia.ollama_client import OllamaClient, IAError


def diagnosticar_base(settings: Settings) -> dict:
    result = {"estado": "no_configurada", "postgres_version": None,
              "pgvector_disponible": False, "pgvector_instalado": None,
              "permiso_create": None, "normas_activas": None,
              "vector_store": "no_verificado", "normas_vectorizadas": 0}
    if not settings.database_url:
        return result
    engine = None
    try:
        url = make_url(normalizar_url(settings.database_url))
        if url.get_backend_name() != "postgresql":
            return {**result, "estado": "requiere_postgresql"}
        engine = create_engine(url, connect_args={"connect_timeout": 5})
        with engine.connect() as connection:
            connection.execute(text("SET LOCAL statement_timeout = '5000ms'"))
            result["postgres_version"] = connection.scalar(text("SHOW server_version"))
            extension = connection.execute(text(
                "SELECT default_version, installed_version FROM pg_available_extensions "
                "WHERE name = 'vector'"
            )).mappings().first()
            result["pgvector_disponible"] = extension is not None
            result["pgvector_instalado"] = extension["installed_version"] if extension else None
            result["permiso_create"] = connection.scalar(text(
                "SELECT has_database_privilege(current_database(), 'CREATE')"))
            # CREATE no demuestra por sí solo permiso para instalar una extensión no trusted.
            # La instalación efectiva requiere verificación en la fase de migración.
            exists = connection.scalar(text("SELECT to_regclass('public.normas') IS NOT NULL"))
            if exists:
                result["normas_activas"] = connection.scalar(text(
                    "SELECT count(*) FROM normas WHERE activa = true"))
            result["estado"] = "ok"
            vectors = connection.scalar(text("SELECT to_regclass('public.norma_embeddings') IS NOT NULL"))
            result["vector_store"] = "ok" if vectors and extension and extension["installed_version"] else "pendiente_migracion"
            if vectors:
                result["normas_vectorizadas"] = connection.scalar(text(
                    "SELECT count(*) FROM norma_embeddings e JOIN normas n ON n.id=e.norma_id "
                    "WHERE n.activa AND e.modelo=:modelo AND e.dimension=1024"),
                    {"modelo": settings.embedding_model})
    except Exception:
        # Los mensajes de conexión pueden contener host, usuario o contraseña.
        result["estado"] = "error_conexion_o_inspeccion"
    finally:
        if engine is not None:
            engine.dispose()
    return result


def diagnosticar(settings: Settings | None = None, medir_embedding: bool = False) -> dict:
    settings = settings or get_settings()
    # Sin el cache de chequeos previos: un diagnostico que repite lo que vio hace cinco
    # minutos diria "ok" con Ollama caido, que es justo lo que se viene a averiguar.
    client = OllamaClient(settings.model_copy(update={"ollama_preflight_ttl": 0}))
    result = {"ollama_disponible": False, "modelo_principal_disponible": False,
              "embedding_disponible": False, "embedding_dimensiones": None,
              "modelo_principal": settings.ollama_model,
              "embedding_modelo": settings.embedding_model,
              "mensaje": None}
    try:
        models = client.modelos()
        result["ollama_disponible"] = True
        for model, capability, field in [
            (settings.ollama_model, "completion", "modelo_principal_disponible"),
            (settings.embedding_model, "embedding", "embedding_disponible"),
        ]:
            if model in models:
                try:
                    client.comprobar_modelo(model, capability)
                    result[field] = True
                except IAError:
                    pass
        if medir_embedding and result["embedding_disponible"]:
            result["embedding_dimensiones"] = len(client.embeddings([
                "prueba técnica de disponibilidad"
            ])[0])
    except IAError as exc:
        result["mensaje"] = str(exc)
    result["base"] = diagnosticar_base(settings)
    result["rag_disponible"] = False
    if result["base"]["vector_store"] == "ok" and result["embedding_disponible"]:
        from sqlalchemy.orm import Session
        from sqlalchemy import select
        from app.core.database import crear_engine
        from app.models.conocimiento.norma import Norma
        from app.models.conocimiento.embedding import NormaEmbedding
        from app.services.ia.embeddings import documento_norma, huella_documento
        engine = crear_engine(settings)
        try:
            with Session(engine) as db:
                rows = db.execute(select(Norma, NormaEmbedding.contenido_hash,
                    NormaEmbedding.modelo_digest).join(NormaEmbedding, Norma.id == NormaEmbedding.norma_id)
                    .where(Norma.activa.is_(True), NormaEmbedding.modelo == settings.embedding_model)).all()
                current = sum(digest == models[settings.embedding_model] and
                    fingerprint == huella_documento(documento_norma(n)) for n, fingerprint, digest in rows)
                result["base"]["vectores_actuales"] = current
                result["base"]["faltantes_o_desactualizados"] = result["base"]["normas_activas"] - current
                result["rag_disponible"] = bool(settings.ia_enabled and result["modelo_principal_disponible"]
                    and current > 0 and current == result["base"]["normas_activas"])
        except Exception:
            result["base"]["vector_store"] = "error_verificacion"
        finally:
            if engine is not None:
                engine.dispose()
    return result
