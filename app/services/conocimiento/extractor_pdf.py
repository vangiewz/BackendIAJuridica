import re
from pathlib import Path
from pypdf import PdfReader

def extraer_texto(ruta: Path, ruido: re.Pattern) -> str:
    """Texto del PDF sin las lineas de cabecera que se repiten en cada pagina."""
    reader = PdfReader(ruta)
    lineas_limpias = []
    
    for page in reader.pages:
        texto_pagina = page.extract_text()
        if not texto_pagina:
            continue
            
        for linea in texto_pagina.split('\n'):
            linea_strip = linea.strip()
            if linea_strip and not ruido.match(linea_strip):
                lineas_limpias.append(linea_strip)
                
    return '\n'.join(lineas_limpias)
