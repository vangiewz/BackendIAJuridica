"""Un artículo real por vector; el hash incluye todos los metadatos suministrados."""
import hashlib
import json
from app.models.conocimiento.norma import Norma
from app.services.ia.ollama_client import OllamaClient

VERSION_TEXTO = "norma-v2"


def documento_norma(norma: Norma) -> str:
    if not norma.activa:
        raise ValueError("No se indexan versiones inactivas")
    if not norma.texto or not norma.texto.strip():
        raise ValueError("La norma no tiene texto")
    campos = ("id", "codigo", "articulo", "numero_articulo", "epigrafe", "texto",
              "libro", "parte", "titulo", "capitulo", "seccion", "area_juridica",
              "version", "activa", "estado_vigencia", "nota_vigencia", "vigente_desde",
              "vigente_hasta", "fuente_nombre", "fuente_url", "descargada_en")
    data = {}
    for campo in campos:
        value = getattr(norma, campo)
        data[campo] = getattr(value, "value", value)
    return json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)


def huella_documento(texto: str) -> str:
    return hashlib.sha256((VERSION_TEXTO + "\n" + texto).encode("utf-8")).hexdigest()


def texto_para_embedding(norma: Norma) -> str:
    """Texto legal compacto; identidad, procedencia y vigencia permanecen en el hash/BD."""
    documento_norma(norma)  # valida actividad y contenido
    return "\n".join(str(value) for value in (
        norma.codigo, norma.articulo, norma.libro, norma.parte, norma.titulo,
        norma.capitulo, norma.seccion, norma.epigrafe, norma.texto,
    ) if value)


def embedding_consulta(client: OllamaClient, consulta: str) -> list[float]:
    # Instrucción de recuperación recomendada por Qwen para el lado de la consulta.
    texto = ("Instruct: Retrieve Bolivian civil law articles relevant to the legal question."
             "\nQuery: " + consulta)
    return client.embeddings([texto])[0]
