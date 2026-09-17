from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """Base declarativa unica: todas las entidades del proyecto heredan de aqui."""
    pass
