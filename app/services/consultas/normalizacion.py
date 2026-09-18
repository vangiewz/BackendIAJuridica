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
