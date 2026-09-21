import time
from app.services.ia.cache_modelos import modelos_cacheados, modelo_comprobado, limpiar_cache

def test_cache_modelos_exitosos():
    limpiar_cache()
    llamadas = []
    
    def consultar():
        llamadas.append(1)
        return {"modelo": "hash"}
        
    res1 = modelos_cacheados("url1", 10, consultar)
    res2 = modelos_cacheados("url1", 10, consultar)
    
    assert res1 == res2 == {"modelo": "hash"}
    assert len(llamadas) == 1

def test_cache_modelos_comprobados():
    limpiar_cache()
    llamadas = []
    
    def comprobar():
        llamadas.append(1)
        
    modelo_comprobado("url1", "mod", "cap", 10, comprobar)
    modelo_comprobado("url1", "mod", "cap", 10, comprobar)
    
    assert len(llamadas) == 1

def test_ttl_cero_desactiva_cache():
    limpiar_cache()
    llamadas = []
    
    def comprobar():
        llamadas.append(1)
        
    modelo_comprobado("url1", "mod", "cap", 0, comprobar)
    modelo_comprobado("url1", "mod", "cap", 0, comprobar)
    
    assert len(llamadas) == 2

def test_fallo_no_se_cachea():
    limpiar_cache()
    llamadas = []
    
    def comprobar():
        llamadas.append(1)
        if len(llamadas) == 1:
            raise ValueError("falla")
            
    try:
        modelo_comprobado("url1", "mod", "cap", 10, comprobar)
    except ValueError:
        pass
        
    # El siguiente intento debería llamar de nuevo
    modelo_comprobado("url1", "mod", "cap", 10, comprobar)
    
    assert len(llamadas) == 2
