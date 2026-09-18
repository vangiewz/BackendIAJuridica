from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.conocimiento.esquemas import ResultadoBusqueda, ArticuloDetalle, NodoIndice
from app.controllers.conocimiento.consulta_normas_controller import (
    buscar_normativa, leer_articulo, obtener_indice, ArticuloNoEncontradoError
)

router = APIRouter(prefix="/normativa", tags=["normativa"])

@router.get("/buscar", response_model=ResultadoBusqueda)
def endpoint_buscar(
    q: str = Query(..., description="Texto a buscar"),
    area: str | None = Query(None, description="Area juridica para filtrar"),
    limite: int = Query(20, ge=1, le=100),
    desplazamiento: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Búsqueda full-text en la normativa."""
    return buscar_normativa(db, consulta=q, area=area, limite=limite, desplazamiento=desplazamiento)

@router.get("/articulos/{codigo}/{numero}", response_model=ArticuloDetalle)
def endpoint_leer_articulo(
    codigo: str,
    numero: int,
    db: Session = Depends(get_db)
):
    """Leer un artículo en detalle con navegación."""
    try:
        return leer_articulo(db, codigo, numero)
    except ArticuloNoEncontradoError:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")

@router.get("/indice", response_model=list[NodoIndice])
def endpoint_obtener_indice(
    codigo: str = Query(..., description="Código a consultar"),
    db: Session = Depends(get_db)
):
    """Obtener el índice jerárquico de la normativa."""
    return obtener_indice(db, codigo)
