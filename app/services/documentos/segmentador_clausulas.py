import re
from dataclasses import dataclass
from app.services.shared.normalizacion import normalizar

@dataclass(frozen=True)
class Clausula:
    orden: int
    encabezado: str
    ordinal: str | None
    texto: str
    inicio: int
    fin: int

def segmentar(texto: str) -> list[Clausula]:
    """Aisla las secciones del documento para limitar el alcance de la extraccion y dar trazabilidad."""
    if not texto:
        return []

    patron = re.compile(
        r'^[ \t]*(?:'
        r'(CL[AÁaá]USULA\s+([A-Za-z]+|\d+))'
        r'|'
        r'((PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA|SEXTA|S[EÉeé]PTIMA|OCTAVA|NOVENA|D[EÉeé]CIMA|UND[EÉeé]CIMA|DUOD[EÉeé]CIMA|D[EÉeé]CIMO\s*[A-Za-z]*|VIG[EÉeé]SIMA)\s*[\.\-\:]+)'
        r'|'
        r'(ART[IÍií]CULO\s+(\d+))'
        r').*',
        re.MULTILINE | re.IGNORECASE
    )

    clausulas = []
    matches = list(patron.finditer(texto))
    
    if not matches:
        return []

    for i, match in enumerate(matches):
        inicio_encabezado = match.start()
        fin_encabezado = match.end()
        encabezado = match.group(0).strip()
        
        # Determinar ordinal
        ordinal = None
        if match.group(2): # CLAUSULA (ordinal)
            ordinal = match.group(2)
        elif match.group(4): # ORDINAL.-
            ordinal = match.group(4)
        elif match.group(6): # ARTICULO (num)
            ordinal = match.group(6)
            
        if ordinal:
            ordinal = normalizar(ordinal).upper().strip()

        # Inicio de texto (después del salto de línea si hay)
        inicio_texto = fin_encabezado
        if inicio_texto < len(texto) and texto[inicio_texto] == '\n':
            inicio_texto += 1
            
        fin_texto = matches[i+1].start() if i + 1 < len(matches) else len(texto)
        
        cuerpo = texto[inicio_texto:fin_texto]
        
        clausulas.append(Clausula(
            orden=i+1,
            encabezado=encabezado,
            ordinal=ordinal,
            texto=cuerpo,
            inicio=inicio_encabezado,
            fin=fin_texto
        ))

    return clausulas
