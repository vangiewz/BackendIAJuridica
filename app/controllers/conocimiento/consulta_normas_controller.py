from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.models.conocimiento.norma import Norma
from app.models.conocimiento.esquemas import NormaResumen, ResultadoBusqueda, ArticuloDetalle, Ubicacion, NodoIndice
from app.services.conocimiento.busqueda_lexica import buscar

class ArticuloNoEncontradoError(Exception):
    pass

def buscar_normativa(db: Session, consulta: str, area: str | None = None, limite: int = 20, desplazamiento: int = 0) -> ResultadoBusqueda:
    total, resultados = buscar(db, consulta, area, limite, desplazamiento)
    
    resumenes = []
    for row in resultados:
        norma, relevancia, fragmento = row[0], row[1], row[2]
        resumenes.append(NormaResumen(
            id=norma.id, codigo=norma.codigo, articulo=norma.articulo,
            numero_articulo=norma.numero_articulo, epigrafe=norma.epigrafe,
            fragmento=fragmento, area_juridica=norma.area_juridica,
            libro=norma.libro, relevancia=relevancia, estado_vigencia=norma.estado_vigencia
        ))
        
    return ResultadoBusqueda(consulta=consulta, total=total, resultados=resumenes)

def leer_articulo(db: Session, codigo: str, numero: int) -> ArticuloDetalle:
    stmt = select(Norma).where(Norma.codigo == codigo, Norma.numero_articulo == numero, Norma.activa == True)
    norma = db.execute(stmt).scalar_one_or_none()
    
    if not norma:
        raise ArticuloNoEncontradoError()
        
    anterior = db.scalar(select(func.max(Norma.numero_articulo)).where(
        Norma.codigo == codigo, Norma.numero_articulo < numero, Norma.activa == True))
        
    siguiente = db.scalar(select(func.min(Norma.numero_articulo)).where(
        Norma.codigo == codigo, Norma.numero_articulo > numero, Norma.activa == True))
    
    ubicacion = Ubicacion(libro=norma.libro, parte=norma.parte, titulo=norma.titulo, 
                          capitulo=norma.capitulo, seccion=norma.seccion)
    
    return ArticuloDetalle(
        id=norma.id, codigo=norma.codigo, articulo=norma.articulo, numero_articulo=norma.numero_articulo,
        epigrafe=norma.epigrafe, texto=norma.texto, area_juridica=norma.area_juridica, ubicacion=ubicacion,
        anterior=anterior, siguiente=siguiente, estado_vigencia=norma.estado_vigencia,
        nota_vigencia=norma.nota_vigencia, fuente_nombre=norma.fuente_nombre, fuente_url=norma.fuente_url
    )

def _agregar_nodo(padre_lista: list[NodoIndice], tipo: str, nombre: str, numero: int) -> NodoIndice:
    if padre_lista and padre_lista[-1].tipo == tipo and padre_lista[-1].nombre == nombre:
        return padre_lista[-1]
    nuevo = NodoIndice(
        tipo=tipo, nombre=nombre, desde=numero, hasta=numero, cantidad=0, numeros=[], hijos=[]
    )
    padre_lista.append(nuevo)
    return nuevo

def obtener_indice(db: Session, codigo: str) -> list[NodoIndice]:
    stmt = select(Norma.libro, Norma.parte, Norma.titulo, Norma.capitulo, Norma.seccion, Norma.numero_articulo)\
           .where(Norma.codigo == codigo, Norma.activa == True)\
           .order_by(Norma.numero_articulo.asc())
    rows = db.execute(stmt).all()
    
    raiz = []
    for libro, parte, titulo, capitulo, seccion, numero in rows:
        current = raiz
        camino = []
        for tipo, valor in [("libro", libro), ("parte", parte), ("titulo", titulo), 
                            ("capitulo", capitulo), ("seccion", seccion)]:
            if valor:
                nodo = _agregar_nodo(current, tipo, valor, numero)
                camino.append(nodo)
                current = nodo.hijos
                
        for nodo in camino:
            nodo.desde = min(nodo.desde, numero)
            nodo.hasta = max(nodo.hasta, numero)
            nodo.cantidad += 1
            
        if camino:
            # No se vacía 'numeros' en nodos con hijos porque hay nodos (ej: servidumbres
            # forzosas, arts. 260-261) que tienen artículos propios antes de sus subsecciones.
            camino[-1].numeros.append(numero)
            
    return raiz
