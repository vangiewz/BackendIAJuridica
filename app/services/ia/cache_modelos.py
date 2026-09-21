"""Memo con vencimiento para los chequeos previos de modelo en Ollama."""

import time
from typing import Callable
from threading import Lock

# Caches globales seguros entre hilos
_tags_cache: dict[str, tuple[float, dict[str, str]]] = {}
_comprobados_cache: dict[tuple[str, str, str], float] = {}
_lock = Lock()

def modelos_cacheados(url: str, ttl: int, consultar: Callable[[], dict[str, str]]) -> dict[str, str]:
    """Resultado de /api/tags por URL. Con ttl=0 no cachea: siempre llama a `consultar`."""
    if ttl == 0:
        return consultar()
        
    ahora = time.monotonic()
    
    with _lock:
        if url in _tags_cache:
            expiracion, datos = _tags_cache[url]
            if ahora < expiracion:
                return datos
                
    # Llamar sin el lock retenido para no bloquear otros hilos que busquen otras URLs
    resultado = consultar()
    
    with _lock:
        _tags_cache[url] = (ahora + ttl, resultado)
        
    return resultado

def modelo_comprobado(url: str, modelo: str, capability: str, ttl: int,
                      comprobar: Callable[[], None]) -> None:
    """Memo de que (modelo, capability) paso el chequeo. Con ttl=0 siempre comprueba."""
    if ttl == 0:
        return comprobar()
        
    clave = (url, modelo, capability)
    ahora = time.monotonic()
    
    with _lock:
        if clave in _comprobados_cache and ahora < _comprobados_cache[clave]:
            return
            
    # Llamar sin el lock retenido para no bloquear otros hilos
    comprobar()
    
    with _lock:
        _comprobados_cache[clave] = ahora + ttl

def limpiar_cache() -> None:
    """Vacia el memo. Para los tests y para forzar una relectura del estado real."""
    with _lock:
        _tags_cache.clear()
        _comprobados_cache.clear()
