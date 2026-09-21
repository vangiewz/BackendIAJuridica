# Backend

API FastAPI del Sistema Inteligente de Asistencia Juridica Civil Boliviana. La IA corre **local**
con Ollama (`qwen3:8b` para responder y `qwen3-embedding:0.6b` para buscar); no usa servicios en la nube.

Pipeline por defecto (`IA_PIPELINE=simple`): pregunta -> busqueda hibrida -> fuentes -> una llamada a Qwen -> validacion basica.

# Ejecutar Backend IA en Windows con NVIDIA

Objetivo: en una PC Windows nueva, del `git clone` al backend funcionando usando la GPU.

## 1. Requisitos

- **Git**.
- **Python 3.13** (es la version con la que se desarrollo y probo; <https://www.python.org/downloads/>, marca *Add python.exe to PATH*).
- **Driver NVIDIA** actualizado. No hace falta instalar el CUDA Toolkit: Ollama trae lo que necesita.
- **Ollama** para Windows: <https://ollama.com/download>.
- La **cadena `DATABASE_URL`** de la base PostgreSQL/Neon actual (se pide al equipo; no esta en el repositorio).
- Unos 8 GB libres en disco para los modelos.

## 2. Comprobar la GPU

```powershell
nvidia-smi
ollama --version
```

`nvidia-smi` debe listar la RTX y su driver.

## 3. Clonar

```powershell
git clone https://github.com/vangiewz/BackendIAJuridica.git
cd BackendIAJuridica
```

## 4-7. Instalacion automatica (recomendado)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
```

Hace, en orden y de forma repetible: comprueba Python, crea `.venv`, instala `requirements.txt`, crea `.env`
**solo si no existe**, revisa la GPU y Ollama, ofrece descargar los modelos que falten (pregunta antes) y
ejecuta `python -m scripts.verificar_entorno`. No instala drivers, no toca el firewall, no borra nada y no
ejecuta migraciones.

### Los mismos pasos, a mano

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env        # y editar .env (ver mas abajo)

ollama pull qwen3:8b
ollama pull qwen3-embedding:0.6b
ollama list                        # deben aparecer los dos
```

## 6. Configurar `.env`

Editar `.env` y completar **solo estas dos** (el resto ya trae el valor recomendado):

- `DATABASE_URL`: la cadena real de PostgreSQL/Neon (`postgresql+psycopg://USUARIO:CLAVE@HOST/BASE?sslmode=require`).
- `JWT_SECRET`: opcional en desarrollo (se genera uno aleatorio en cada arranque, y las sesiones abiertas dejan de valer al reiniciar). Para uno fijo:
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

Ademas, `IA_PIPELINE=simple` (default recomendado). `.env` esta en `.gitignore`: nunca se sube.

Por ahora se sigue usando la base actual; **no hay que regenerar embeddings ni migrar nada**: la normativa y sus vectores ya estan en la base.

## 8. Verificar y calentar los modelos

```powershell
python -m scripts.verificar_entorno   # paquetes, .env, Ollama, modelos y base (ligero, no genera texto)
python -m scripts.warmup_ia           # carga los modelos en memoria (GPU); no consulta ni escribe en la base
```

## 9. Arrancar FastAPI

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

(o `.\scripts\start_backend.ps1`, que ademas muestra la IP de la PC). Con `--host 0.0.0.0` el backend acepta conexiones de otros equipos.

## 10. Comprobar

Abrir <http://localhost:8000/api/v1/health>: debe responder `{"status":"ok", ... "database":"ok"}`.

## 11. Comprobar que usa la GPU

Despues del warm-up (o de una consulta):

```powershell
ollama ps        # la columna PROCESSOR debe decir 100% GPU
nvidia-smi       # debe verse ollama.exe usando memoria de la GPU
nvidia-smi -l 1  # opcional: refresca cada segundo mientras se responde
```

Si `ollama ps` dice `CPU`, revisa el driver (`nvidia-smi`) y reinicia Ollama. Los embeddings de las
consultas se calculan en CPU a proposito (`EMBEDDING_NUM_GPU=0`, valor validado); no es un error.

## 12. Usarlo desde otra PC o el celular por LAN

1. Arrancar con `--host 0.0.0.0` (paso 9).
2. Obtener la IP de esta PC: `ipconfig` -> *Direccion IPv4*.
3. Puede ser necesario abrir **solo el puerto TCP 8000** en el firewall de Windows (PowerShell como administrador):

   ```powershell
   New-NetFirewallRule -DisplayName "Backend juridico 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
   ```

   Si la red esta marcada como *Public*, cambiarla a *Private* (`Get-NetConnectionProfile`, `Set-NetConnectionProfile`).
4. Desde el otro equipo: `http://IP_DE_ESTA_PC:8000/api/v1/health`.

**No abras el puerto 11434 (Ollama) a la red.** Ollama se queda escuchando en loopback. Si querés que
el equipo le consulte a tu GPU, no abras el puerto: usá el tunel autenticado de
[Servir la IA al equipo](#servir-la-ia-al-equipo).

## Problemas frecuentes

| Sintoma | Causa probable |
|---|---|
| `verificar_entorno` dice *no responde en http://127.0.0.1:11434* | Ollama no esta abierto: iniciar la app o `ollama serve`. |
| Falta un modelo | `ollama pull qwen3:8b` / `ollama pull qwen3-embedding:0.6b`. |
| `database: error` en `/health` | `DATABASE_URL` incorrecta, o sin internet para llegar a Neon. |
| `ollama ps` muestra CPU | Driver NVIDIA ausente o desactualizado; ver `nvidia-smi`. |
| Otro equipo no llega al backend | Falta `--host 0.0.0.0`, la regla de firewall o la red esta en *Public*. |

# Referencia

## Docker
Ejecutar: `docker compose up --build`

## Despliegue en Azure

La API publicada corre en **Azure App Service for Containers** (Linux, plan B1, region
`eastus`), con la imagen guardada en Azure Container Registry.

| Recurso | Nombre |
|---|---|
| Grupo de recursos | `rg-ia-juridica-eus` |
| Registro | `acriajuridica.azurecr.io` |
| Plan | `plan-ia-juridica` (Linux B1) |
| Sitio | `ia-juridica-api` |
| URL | `https://ia-juridica-api.azurewebsites.net` |

Para publicar una version nueva, con el repositorio en el commit que se quiere desplegar:

```bash
TAG=$(git rev-parse --short HEAD)
az acr build --registry acriajuridica --image ia-juridica-api:$TAG --platform linux/amd64 .
az webapp config container set -g rg-ia-juridica-eus -n ia-juridica-api \
  --container-image-name acriajuridica.azurecr.io/ia-juridica-api:$TAG
az webapp restart -g rg-ia-juridica-eus -n ia-juridica-api
curl https://ia-juridica-api.azurewebsites.net/api/v1/health
```

El nombre de imagen ya incluye el registro: no pasarle ademas `--container-registry-url`, o
Azure duplica el host y el pull falla con `ImagePullUnauthorizedFailure`.

En la nube no hay Ollama, asi que el sitio corre con **`IA_ENABLED=false`** y las consultas
usan el respaldo lexico sobre la normativa. Las variables de entorno no viven en un `.env`
sino en las *app settings* del sitio:

```bash
az webapp config appsettings list -g rg-ia-juridica-eus -n ia-juridica-api --query "[].name" -o tsv
az webapp config appsettings set -g rg-ia-juridica-eus -n ia-juridica-api --settings CORS_ORIGINS="..."
```

Ademas de las de la tabla de abajo, el sitio necesita `WEBSITES_PORT=8000` para que Azure sepa
a que puerto hablarle.

## Servir la IA al equipo

El backend en Azure no tiene GPU, asi que la inferencia la puede dar una PC del equipo. Lo unico
que se publica es **Ollama**, detras de un tunel de Cloudflare con token: el resto del sistema no
cambia.

```
App (Vercel)  ->  API (Azure)  ->  https://ia.<dominio>  ->  cloudflared  ->  127.0.0.1:11434
```

### Consultarle la IA a otra maquina

Es **una sola variable**. Con el token ya puesto en tu `.env` (se ignora cuando la URL es
loopback, asi que podes dejarlo ahi para siempre):

```bash
OLLAMA_URL=http://127.0.0.1:11434      # mi propio Ollama
OLLAMA_URL=https://ia.<dominio>        # la PC con GPU del equipo
```

Comprobalo con `python -m scripts.diagnosticar_ia`: tiene que listar los dos modelos y medir un
embedding.

### Servir la IA desde esta PC

Requiere `cloudflared` instalado y un tunel ya creado en el panel de Cloudflare Zero Trust,
apuntando a `http://127.0.0.1:11434`, con una politica de **Service Auth** sobre el hostname.

```powershell
.\scripts\servir_ia.ps1 -Tunel <nombre-del-tunel> -Hostname ia.<dominio>
```

El script comprueba que Ollama responda, precarga los modelos en la GPU y levanta el tunel.
Mientras corra, el equipo tiene IA; con `Ctrl+C` deja de servir y las consultas vuelven al
respaldo lexico. **No hay que abrir ningun puerto ni tocar el firewall**: `cloudflared` abre una
conexion hacia afuera, asi que funciona incluso detras de CGNAT, y Ollama se queda en loopback.

### Dos limites que conviene saber

- **100 segundos.** El plan gratis de Cloudflare corta la peticion si el origen no empieza a
  responder en 100 s, y el cliente no usa streaming. Una consulta normal promedia 34 s, pero el
  flujo de *caso complejo* (timeout de 600 s) no entra: queda para uso local. Por eso con el
  tunel se usa `OLLAMA_TIMEOUT=95`, para cortar antes y dar un error limpio en vez de un 524.
- **Si la PC se apaga, no se rompe nada.** El fallo se traduce a `IANoDisponible` y la consulta
  responde con el respaldo lexico sobre la normativa, citando fuentes igual (HU-05). Es el mismo
  camino que con `IA_ENABLED=false`.

## Variables de entorno

Ver `.env.example` (cada variable esta comentada). Las principales:

| Variable | Descripcion | Obligatoria | Ejemplo |
|---|---|---|---|
| `DATABASE_URL` | Cadena de conexion a PostgreSQL (Neon) | Si | `postgresql+psycopg://user:pass@host/dbname?sslmode=require` |
| `ENVIRONMENT` | Entorno (`development`, `production`) | No | `development` |
| `JWT_SECRET` | Clave para firmar tokens JWT | Si (salvo en development) | *(generar uno)* |
| `JWT_ACCESS_MINUTOS` / `JWT_REFRESH_DIAS` | Vigencia de los tokens | No | `30` / `7` |
| `IA_PIPELINE` | `simple` (recomendado) o `advanced` | No | `simple` |
| `IA_ENABLED` | `false` apaga la IA y deja el respaldo lexico (obligatorio donde no hay Ollama, p. ej. en la nube) | No | `true` |
| `CORS_ORIGINS` | Origenes web autorizados, separados por coma | No | `https://mi-frontend.vercel.app,http://localhost:8081` |
| `CORS_ORIGIN_REGEX` | Patron extra de origenes (previews de Vercel). Vacio lo desactiva | No | `^https://ia-juridica[\w-]*\.vercel\.app$` |
| `OLLAMA_URL` | A donde se le pide la inferencia: loopback sobre `http`, o remoto sobre `https` con credenciales | No | `http://127.0.0.1:11434` |
| `CF_ACCESS_CLIENT_ID` / `CF_ACCESS_CLIENT_SECRET` | Service token de Cloudflare Access. Obligatorias si `OLLAMA_URL` es remoto; se ignoran si es loopback | Solo con IA remota | *(las da quien sirve la IA)* |
| `OLLAMA_CONNECT_TIMEOUT` | Segundos para establecer la conexion (`10` con el tunel de por medio) | No | `3` |
| `OLLAMA_PREFLIGHT_TTL` | Vigencia del cache de chequeos de modelo, en segundos. `0` lo desactiva | No | `300` |
| `OLLAMA_TIMEOUT` | Espera de la respuesta del modelo. Con el tunel, `95` (Cloudflare corta a los 100 s) | No | `180` |
| `OLLAMA_MODEL` / `EMBEDDING_MODEL` | Modelos locales | No | `qwen3:8b` / `qwen3-embedding:0.6b` |
| `OLLAMA_NUM_CTX` | Ventana de contexto | No | `8192` |

## Migraciones de Base de Datos (Alembic)

Para aplicar las migraciones (solo en una base nueva y vacia; la base actual ya las tiene):
`alembic upgrade head`

## Comandos

### Ingesta Normativa
Para sincronizar los articulos del Codigo Civil a la base de datos (parsea, ingiere y genera un reporte de manera idempotente):
```bash
python -m scripts.ingesta_normativa --fuente codigo_civil
```
Usa el flag `--dry-run` para parsear y armar el reporte sin escribir en la base de datos:
```bash
python -m scripts.ingesta_normativa --fuente codigo_civil --dry-run
```
