import unicodedata
import re

def normalizar(texto: str) -> str:
    """Minusculas y sin acentos, para que 'Usucapión' y 'usucapion' sean lo mismo."""
    if not texto:
        return ""
    texto_norm = unicodedata.normalize('NFD', texto.lower())
    return ''.join(c for c in texto_norm if unicodedata.category(c) != 'Mn')

def tokenizar(texto: str) -> list[str]:
    """Palabras normalizadas de 3 o mas letras."""
    texto_norm = normalizar(texto)
    tokens = re.findall(r'\b\w+\b', texto_norm)
    return [t for t in tokens if len(t) >= 3]

def sanear_nombre_archivo(texto: str, respaldo: str = "documento", limite: int = 60) -> str:
    """Un nombre de archivo seguro: sin rutas, sin acentos y sin caracteres raros.

    El texto puede venir del titulo de un documento o de un reporte, asi que nunca se
    usa tal cual: se reduce a letras, numeros y guiones bajos antes de llegar a una
    cabecera HTTP. No se construye ninguna ruta con el.
    """
    plano = re.sub(r"[^a-z0-9]+", "_", normalizar(texto)).strip("_")
    return (plano or respaldo)[:limite]
