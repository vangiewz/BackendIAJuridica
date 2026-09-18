"""migracion vacia a proposito (ver nota)

Revision ID: 9a03e8aa9ccb
Revises: 19fe03e0e270
Create Date: 2026-09-18 17:12:15.985434

`alembic revision --autogenerate` genero esta migracion con un solo contenido: borrar la
columna `normas.busqueda` y su indice GIN. Esa columna es un tsvector generado que vive SOLO
aca en las migraciones y **a proposito no esta declarada en el modelo** -- SQLite no sabe
compilar TSVECTOR y la suite offline crea las tablas con `Base.metadata.create_all`.

Autogenerate compara el modelo contra la base, no ve la columna del lado del modelo, y
concluye que sobra. Llego a aplicarse: dejo la busqueda full-text rota hasta que se restauro
a mano.

La migracion se deja vacia en vez de borrarse porque ya figura como aplicada en la base y
quitarla del arbol romperia la cadena de revisiones.

Para que no vuelva a pasar, `migrations/env.py` excluye `normas.busqueda` y su indice de la
comparacion de autogenerate.
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = '9a03e8aa9ccb'
down_revision: Union[str, None] = '19fe03e0e270'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
