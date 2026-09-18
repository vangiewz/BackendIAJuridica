from dataclasses import dataclass
import re

@dataclass(frozen=True)
class PerfilFuente:
    """Todo lo que cambia entre una fuente normativa y otra, en un solo lugar."""
    codigo: str                 # "Codigo Civil"
    fuente_nombre: str          # "OEA / InfoLeyes - texto base DL 12760"
    fuente_url: str
    archivo: str                # ruta relativa dentro de data/normativa/
    total_esperado: int         # 1570 — el parser falla si no llega a este numero
    ruido: re.Pattern           # lineas de cabecera de pagina a descartar
    inicio_articulo: re.Pattern
    nivel: re.Pattern

CODIGO_CIVIL = PerfilFuente(
    codigo="Codigo Civil",
    fuente_nombre="OEA / InfoLeyes - texto base DL 12760",
    fuente_url="https://www.oas.org/dil/esp/codigo_civil_bolivia.pdf",
    archivo="codigo_civil_oea.pdf",
    total_esperado=1570,
    ruido=re.compile(r'^(CODIGO CIVIL - .*InfoLeyes.*|http://bolivia\.infoleyes\.com/.*|CODIGO CIVIL)$'),
    inicio_articulo=re.compile(r'^ART[IÍ]CULO\s+(\d+)\s*[\.\-]', re.M),
    nivel=re.compile(r'^(LIBRO|PARTE|TITULO|CAPITULO|SECCION|SUBSECCION)\s+(\S+)\s*$')
)
