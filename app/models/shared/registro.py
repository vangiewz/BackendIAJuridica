"""Importa todas las entidades para que Alembic las descubra.

Alembic solo ve las tablas registradas en Base.metadata, y eso ocurre cuando el
modulo de cada entidad se importa. Sin este registro, autogenerate genera
migraciones vacias o, peor, propone borrar tablas existentes.
"""

# Importar modelos existentes
from app.models.auth.usuario import Usuario

# Importar nuevos modelos de los dominios
from app.models.consultas.consulta import Consulta
from app.models.consultas.fuente_legal import FuenteLegal
from app.models.conocimiento.norma import Norma
from app.models.documentos.documento import Documento
from app.models.documentos.analisis import AnalisisDocumento
from app.models.documentos.comparacion import ComparacionDocumentos
from app.models.contratos.riesgo import RiesgoContractual
from app.models.generacion.documento_generado import DocumentoGenerado

# Para que el linter no se queje de imports no usados
__all__ = [
    "Usuario",
    "Consulta",
    "FuenteLegal",
    "Norma",
    "Documento",
    "AnalisisDocumento",
    "ComparacionDocumentos",
    "RiesgoContractual",
    "DocumentoGenerado",
]
