import logging
from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
from app.core.config import get_settings
from app.core.database import normalizar_url
from app.models.shared.base import Base

# Importar todos los modelos para que Alembic los detecte
import app.models.shared.registro

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# Objetos que autogenerate NO debe tocar nunca.
#
# `normas.busqueda` es un tsvector generado que vive solo en las migraciones y a proposito no
# esta declarado en el modelo: SQLite no sabe compilar TSVECTOR y la suite offline crea las
# tablas con Base.metadata.create_all. Autogenerate no lo ve del lado del modelo, concluye que
# sobra y genera un DROP COLUMN. El 2026-09-18 eso llego a aplicarse contra la base y dejo la
# busqueda full-text rota.
EXCLUIDOS_DE_AUTOGENERATE = {
    ("column", "normas", "busqueda"),
    ("index", "normas", "ix_normas_busqueda"),
}


def include_object(object, name, type_, reflected, compare_to):
    """Deja fuera de autogenerate lo que se gestiona a mano en SQL."""
    tabla = getattr(object, "table", None)
    nombre_tabla = tabla.name if tabla is not None else getattr(object, "name", None)
    if (type_, nombre_tabla, name) in EXCLUIDOS_DE_AUTOGENERATE:
        return False
    return True


def get_url():
    settings = get_settings()
    url = normalizar_url(settings.database_url)
    return url

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
