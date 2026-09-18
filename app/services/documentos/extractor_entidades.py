from dataclasses import dataclass
from app.services.documentos.segmentador_clausulas import segmentar, Clausula
from app.services.documentos.patrones import (
    MONTO_BOLIVIANOS, MONTO_DOLARES, FECHA_NUMERICA, FECHA_LARGA, CEDULA, NIT, PLAZO, INICIO_PARTES
)

@dataclass(frozen=True)
class Hallazgo:
    tipo: str        # 'monto_bs' | 'monto_usd' | 'fecha' | 'plazo' | 'cedula' | 'nit'
    texto: str       # el fragmento exacto, tal como aparece
    inicio: int      # offset en el texto original
    fin: int
    clausula: int | None   # en que clausula cayo, si cayo en alguna

@dataclass(frozen=True)
class Extraccion:
    hallazgos: tuple[Hallazgo, ...]
    parrafo_partes: str | None
    clausulas: tuple[Clausula, ...]

def extraer(texto: str) -> Extraccion:
    """Lo que se puede reconocer sin interpretar, con la posicion donde aparece."""
    if not texto:
        return Extraccion(tuple(), None, tuple())
        
    clausulas = segmentar(texto)
    hallazgos_list = []
    
    patrones_map = {
        'monto_bs': [MONTO_BOLIVIANOS],
        'monto_usd': [MONTO_DOLARES],
        'fecha': [FECHA_NUMERICA, FECHA_LARGA],
        'cedula': [CEDULA],
        'nit': [NIT],
        'plazo': [PLAZO]
    }
    
    for tipo, patterns in patrones_map.items():
        for patron in patterns:
            for match in patron.finditer(texto):
                inicio = match.start()
                fin = match.end()
                
                claus_id = None
                for c in clausulas:
                    if c.inicio <= inicio < c.fin:
                        claus_id = c.orden
                        break
                
                hallazgos_list.append(Hallazgo(
                    tipo=tipo,
                    texto=match.group(0),
                    inicio=inicio,
                    fin=fin,
                    clausula=claus_id
                ))
    
    # Resolver solapamientos: gana el más largo
    hallazgos_list.sort(key=lambda h: (h.inicio, -(h.fin - h.inicio)))
    
    hallazgos_filtrados = []
    for h in hallazgos_list:
        solapa = False
        for hf in hallazgos_filtrados:
            if h.inicio < hf.fin and h.fin > hf.inicio:
                solapa = True
                break
        if not solapa:
            hallazgos_filtrados.append(h)
            
    hallazgos_filtrados.sort(key=lambda h: h.inicio)
    
    # Parrafo partes
    parrafo_partes = None
    match_partes = INICIO_PARTES.search(texto)
    if match_partes:
        inicio_parrafo = match_partes.start()
        fin_parrafo = len(texto)
        
        idx_doble = texto.find('\n\n', inicio_parrafo)
        if idx_doble != -1:
            fin_parrafo = idx_doble
            
        if clausulas:
            primer_enc = clausulas[0].inicio
            if primer_enc > inicio_parrafo and primer_enc < fin_parrafo:
                fin_parrafo = primer_enc
                
        parrafo_partes = texto[inicio_parrafo:fin_parrafo].strip()
        
    return Extraccion(
        hallazgos=tuple(hallazgos_filtrados),
        parrafo_partes=parrafo_partes,
        clausulas=tuple(clausulas)
    )
