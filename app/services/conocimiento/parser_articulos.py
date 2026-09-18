import re
from dataclasses import dataclass
from typing import Tuple, Dict, Any
from app.services.conocimiento.perfiles_fuente import PerfilFuente

@dataclass(frozen=True)
class ArticuloParseado:
    numero: int
    articulo: str
    epigrafe: str | None
    texto: str
    libro: str | None
    parte: str | None
    titulo: str | None
    capitulo: str | None
    seccion: str | None

def _reiniciar_cascada(tipo: str, num: str, nombre: str, ctx: Dict[str, str | None]):
    valor = f"{tipo} {num} {nombre}".strip()
    if tipo == 'LIBRO':
        ctx['libro'] = valor
        ctx['parte'] = ctx['titulo'] = ctx['capitulo'] = ctx['seccion'] = None
    elif tipo == 'PARTE':
        ctx['parte'] = valor
        ctx['titulo'] = ctx['capitulo'] = ctx['seccion'] = None
    elif tipo == 'TITULO':
        ctx['titulo'] = valor
        ctx['capitulo'] = ctx['seccion'] = None
    elif tipo == 'CAPITULO':
        ctx['capitulo'] = valor
        ctx['seccion'] = None
    elif tipo == 'SECCION':
        ctx['seccion'] = valor
    elif tipo == 'SUBSECCION':
        pass # Se descarta porque Norma no tiene columna subseccion

def _recolectar_bloques(lineas: list[str], perfil: PerfilFuente) -> list[Dict[str, Any]]:
    bloques = []
    ctx = {'libro': None, 'parte': None, 'titulo': None, 'capitulo': None, 'seccion': None}
    cur_num = None
    cur_lines = []
    saved_ctx = ctx.copy()
    i = 0
    while i < len(lineas):
        linea = lineas[i]
        m_nivel = perfil.nivel.match(linea)
        if m_nivel:
            nombre_partes = []
            while i + 1 < len(lineas):
                nxt = lineas[i+1].strip()
                if not nxt or not nxt.isupper():
                    break
                if perfil.nivel.match(nxt) or perfil.inicio_articulo.match(nxt):
                    break
                if re.match(r'^[IVX]+\.', nxt) or nxt.startswith('('):
                    break
                nombre_partes.append(nxt)
                i += 1
            nombre = " ".join(nombre_partes)
            _reiniciar_cascada(m_nivel.group(1), m_nivel.group(2), nombre, ctx)
            i += 1
            continue
        m_art = perfil.inicio_articulo.match(linea)
        if m_art:
            if cur_num is not None:
                bloques.append({"numero": cur_num, "articulo": str(cur_num), **saved_ctx, "texto": '\n'.join(cur_lines)})
            cur_num = int(m_art.group(1))
            saved_ctx = ctx.copy()
            body = linea[m_art.end():]
            cur_lines = [body] if body else []
        elif cur_num is not None:
            cur_lines.append(linea)
        i += 1
    if cur_num is not None:
        bloques.append({"numero": cur_num, "articulo": str(cur_num), **saved_ctx, "texto": '\n'.join(cur_lines)})
    return bloques

def _procesar_epigrafe(texto_bruto: str) -> Tuple[str | None, str]:
    epigrafe_re = re.compile(r'^\s*\(?\s*([^)\n]{0,120}(?:\n[^)\n]{0,120})?)\s*\)\s*[\.\-]{0,2}')
    m_epi = epigrafe_re.match(texto_bruto)
    if not m_epi:
        return None, texto_bruto
    epi_norm = re.sub(r'\s+', ' ', m_epi.group(1)).strip()
    epi_norm = re.sub(r'^[\-\(\s]+', '', epi_norm)
    return epi_norm if epi_norm else None, texto_bruto[m_epi.end():].strip()

def parsear(texto: str, perfil: PerfilFuente) -> list[ArticuloParseado]:
    bloques = _recolectar_bloques(texto.split('\n'), perfil)
    resultados = []
    for b in bloques:
        epigrafe, texto_final = _procesar_epigrafe(b["texto"].strip())
        resultados.append(ArticuloParseado(
            numero=b["numero"],
            articulo=b["articulo"],
            epigrafe=epigrafe,
            texto=texto_final,
            libro=b["libro"],
            parte=b["parte"],
            titulo=b["titulo"],
            capitulo=b["capitulo"],
            seccion=b["seccion"]
        ))
    return resultados
