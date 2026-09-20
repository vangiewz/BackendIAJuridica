from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.core.config import get_settings
from app.core.dependencias import usuario_actual
from app.models.conocimiento.norma import Norma
from app.models.ia.esquemas import BusquedaIAResponse, ExplicacionArticuloIA
from app.services.ia.explicacion import explicar_articulo
from app.models.shared.enums import AreaJuridica
from app.services.conocimiento.busqueda_hibrida import buscar_hibrida
from app.services.ia.fuentes import fuente_de_norma
from app.core.database import get_db
from app.models.conocimiento.esquemas import ResultadoBusqueda, ArticuloDetalle, NodoIndice
from app.controllers.conocimiento.consulta_normas_controller import (
    buscar_normativa, leer_articulo, obtener_indice, ArticuloNoEncontradoError
)

router = APIRouter(prefix="/normativa", tags=["normativa"])


@router.get("/buscar-hibrida", response_model=BusquedaIAResponse)
def endpoint_buscar_hibrida(q: str = Query(..., min_length=3, max_length=2000),
                            limite: int = Query(5, ge=1, le=10),
                            area: AreaJuridica | None = None,
                            db: Session = Depends(get_db), usuario=Depends(usuario_actual)):
    result = buscar_hibrida(db, q, limite, area.value if area else None)
    return BusquedaIAResponse(consulta=q, modo=result.modo,
        resultados=[fuente_de_norma(r.Norma, r) for r in result.resultados],
        tiempos_ms=result.tiempos_ms, advertencia=result.advertencia)

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

@router.get("/articulos/{codigo}/{numero}/explicacion", response_model=ExplicacionArticuloIA)
def endpoint_explicar_articulo(codigo: str, numero: int, db: Session = Depends(get_db),
                               usuario=Depends(usuario_actual)):
    """HU-13: texto original más una explicación sencilla generada localmente."""
    norma = db.scalar(select(Norma).where(Norma.codigo == codigo, Norma.activa.is_(True),
                                          Norma.numero_articulo == numero))
    if not norma:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")
    if not get_settings().ia_enabled:
        return ExplicacionArticuloIA(disponible=False, articulo=norma.articulo,
            texto_original=norma.texto, motivo="La función de IA está desactivada.")
    return explicar_articulo(norma)

@router.get("/indice", response_model=list[NodoIndice])
def endpoint_obtener_indice(
    codigo: str = Query(..., description="Código a consultar"),
    db: Session = Depends(get_db)
):
    """Obtener el índice jerárquico de la normativa."""
    return obtener_indice(db, codigo)
