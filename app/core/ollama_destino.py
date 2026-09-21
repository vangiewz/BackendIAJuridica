"""Politica de destino de Ollama: Ollama no autentica, asi que la URL decide el riesgo."""

from urllib.parse import urlsplit
from ipaddress import ip_address

HOSTS_LOCALES: tuple[str, ...] = ("localhost", "host.docker.internal")

def es_local(url: str) -> bool:
    """True si la URL apunta a la misma maquina: loopback por IP o un nombre de HOSTS_LOCALES."""
    u = urlsplit(url)
    try:
        return u.hostname in HOSTS_LOCALES or ip_address(u.hostname or "").is_loopback
    except ValueError:
        return u.hostname in HOSTS_LOCALES

def validar_destino(url: str) -> str:
    """Normaliza la URL y rechaza los destinos inaceptables. Lanza ValueError con el motivo."""
    u = urlsplit(url)
    
    if u.username or u.password:
        raise ValueError("OLLAMA_URL no debe contener userinfo (disfraz de loopback)")
    
    if u.path not in ("", "/"):
        raise ValueError("OLLAMA_URL no debe contener path")
        
    if u.query or u.fragment:
        raise ValueError("OLLAMA_URL no debe contener query o fragment")

    local = es_local(url)
    
    if local and u.scheme != "http":
        raise ValueError("Un OLLAMA_URL local debe usar esquema http")
        
    if not local and u.scheme != "https":
        raise ValueError("Un OLLAMA_URL remoto debe usar esquema https")
        
    return url.rstrip("/")

def cabeceras_acceso(client_id: str, client_secret: str) -> dict[str, str]:
    """Cabeceras de service token de Cloudflare Access. Diccionario vacio si falta alguna."""
    client_id = client_id.strip()
    client_secret = client_secret.strip()
    if not client_id or not client_secret:
        return {}
    return {"CF-Access-Client-Id": client_id, "CF-Access-Client-Secret": client_secret}
