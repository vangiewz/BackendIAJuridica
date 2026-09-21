# IA local: instalación, operación y estado

La inferencia corre en una máquina del equipo, contra un servidor Ollama propio: por
omisión el de esta PC en loopback, u opcionalmente el de otra PC del equipo detrás de un
túnel autenticado (§15). No se usa ninguna API externa de modelos: la configuración
rechaza los modelos con variante *cloud*, y cualquier destino remoto que no venga sobre
TLS y con credenciales.

## Estado actual

Implementado y verificado contra la base real:

- configuración, cliente Ollama, diagnóstico y embeddings locales;
- almacenamiento vectorial en PostgreSQL con `pgvector` (coseno exacto);
- indexación idempotente de las normas activas;
- búsqueda léxica, vectorial e híbrida con fusión RRF;
- RAG con validación determinista de citas (HU-01, HU-02, HU-04, HU-06);
- resumen y observaciones de contratos (HU-10);
- explicación simplificada de artículos (HU-13);
- generación y versionado de borradores (HU-14, HU-15).

No se hizo fine-tuning. El modelo no es fuente de derecho: la fuente es la
normativa almacenada en PostgreSQL y los resultados deterministas ya existentes.

## Requisitos

- Python 3.11 o superior; se usa Python 3.13.
- Node.js y las dependencias del frontend.
- Ollama local: <https://ollama.com/download>.
- PostgreSQL con la extensión `vector` disponible (verificado con 18.6 y pgvector 0.8.6).

## 1. Directorio de modelos y servidor

`OLLAMA_MODELS` pertenece al **proceso servidor de Ollama**, no al `.env` de FastAPI.
En PowerShell, antes de iniciar el servidor:

```powershell
$env:OLLAMA_MODELS = 'D:\ruta\a\modelos'
ollama serve
```

Si Ollama ya corre desde la bandeja, cerrarlo antes de arrancarlo con otra variable;
no iniciar dos servidores en el mismo puerto. No versionar blobs de modelos.

## 2. Modelos

```powershell
ollama pull qwen3:8b
ollama pull qwen3-embedding:0.6b
ollama list
```

- Generación: `qwen3:8b`.
- Embeddings: `qwen3-embedding:0.6b`, **1024 dimensiones** medidas contra la API real.

El índice guarda modelo, digest y dimensión: si cambia el modelo de embeddings, los
vectores dejan de usarse en lugar de mezclarse con los nuevos.

## 3. Backend y configuración

Desde `BackendIAJuridica`:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Crear `.env` desde `.env.example` **solo si no existe**. `DATABASE_URL` y `JWT_SECRET`
no se comparten ni se versionan (`.gitignore` ya excluye `.env`).

| Variable | Valor por defecto | Uso |
|---|---|---|
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Loopback sobre `http`, o remoto sobre `https` con credenciales (§15) |
| `CF_ACCESS_CLIENT_ID` / `CF_ACCESS_CLIENT_SECRET` | *(vacías)* | Service token; solo se usan si `OLLAMA_URL` es remoto |
| `OLLAMA_MODEL` | `qwen3:8b` | Generación estructurada |
| `OLLAMA_TIMEOUT` | `180` | Timeout de lectura en segundos; conexión: 3 s |
| `OLLAMA_TEMPERATURE` | `0` | Máximo permitido 0.3 |
| `OLLAMA_NUM_CTX` | `4096` | Contexto del modelo generativo |
| `OLLAMA_NUM_PREDICT` | `1800` | Límite de salida por intento |
| `EMBEDDING_MODEL` | `qwen3-embedding:0.6b` | Encoder local |
| `EMBEDDING_NUM_GPU` | `0` | Capas del encoder en GPU; 0 deja la VRAM al generativo |
| `RAG_TOP_K` | `5` | Fuentes que llegan al prompt |
| `RAG_CANDIDATE_K` | `20` | Candidatos por canal antes de la fusión RRF |
| `OLLAMA_KEEP_ALIVE` | `5m` | Mantiene el modelo cargado entre consultas |
| `IA_ENABLED` | `true` | En `false` el backend funciona sin IA |

El backend debe ejecutarse en el mismo host que Ollama: el contenedor Docker no
alcanza el `127.0.0.1` del host.

## 4. Migraciones

```powershell
python -m alembic upgrade head
```

La migración `a10localvector` crea la extensión `vector`, la tabla `norma_embeddings`
(vector de 1024, modelo, digest, dimensión y hash de contenido) y su unicidad por
norma y modelo. `a11iaprogreso` agrega `etapa_ia` e `ia_error` a `consultas`.

Con 1570 artículos se usa **coseno exacto, sin índice aproximado**: a esa escala el
recorrido completo es rápido y un índice HNSW/IVFFlat solo agregaría error de
recuperación y complejidad sin una necesidad medida.

## 5. Indexación

```powershell
python -m scripts.generar_embeddings              # indexa lo que falte o haya cambiado
python -m scripts.generar_embeddings --limite 8   # lote corto, para comprobar el entorno
python -m scripts.generar_embeddings --force      # reindexa todo (rara vez hace falta)
```

Sin `--force` no recalcula nada que no haya cambiado, así que volver a ejecutarlo es
la forma de verificar el índice: informa cuántas normas omitió por estar al día.

Es idempotente: cada norma guarda el hash de su contenido junto al vector, así que
una segunda ejecución omite las normas sin cambios en lugar de recalcularlas.
El texto que se envía al encoder es jurídico y jerárquico (código, artículo, libro,
título, capítulo, sección, epígrafe, texto); no incluye identificadores ni URLs.

## 6. Diagnóstico

```powershell
python -m scripts.diagnosticar_ia
python -m scripts.diagnosticar_ia --medir-embedding
```

Informa modelos, capacidades, conexión PostgreSQL, versión, extensión `vector` y
número de normas activas. No imprime credenciales ni contenido de documentos.

## 7. Cómo funciona una consulta

```text
pregunta natural
  └─ clasificador léxico determinista            (área y términos; no lo decide el modelo)
  └─ guardas de abstención                       (artículo inexistente, pedido de inventar)
  └─ HU-02 interpretación de contexto            → qwen3:8b, validada contra el relato
  └─ expansión de consulta explícita             (vocabulario revisable, sin artículos)
  └─ búsqueda léxica  ┐
     búsqueda vectorial┘→ fusión RRF (k=60)      → Top K normas reales
  └─ prompt central con FUENTES                  → qwen3:8b → JSON con esquema
  └─ validación determinista de citas            (si falla: un reintento, luego abstención)
  └─ respuesta + fuentes + limitaciones          → persistida en `consultas.respuesta`
```

Cada cita se comprueba contra el texto de la norma que el retrieval entregó. Si una
referencia no se puede sustentar, la respuesta no se muestra: se abstiene y deja las
fuentes recuperadas a la vista.

## 8. Levantar el sistema

```powershell
# 1. Ollama (terminal propia)
ollama serve

# 2. Backend, desde BackendIAJuridica
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload

# 3. Frontend, desde FrontendIAJuridica
npm install
npx expo start
```

Si el dispositivo no es esta máquina, configurar `EXPO_PUBLIC_API_URL` con la
dirección del backend accesible desde él.

## 9. Pruebas

```powershell
# Offline: sin Ollama y sin red
python -m pytest -m "not integracion and not ia_local" -q

# Integración: requiere DATABASE_URL real
python -m pytest -m "integracion and not ia_local" -q

# IA local real: requiere Ollama y los dos modelos
$env:RUN_IA_LOCAL = '1'
python -m pytest -m ia_local -q
Remove-Item Env:RUN_IA_LOCAL
```

Las pruebas offline no llaman a Ollama: un fixture desactiva `ia_enabled` en todo
test que no esté marcado `ia_local`. El cliente se prueba con `httpx.MockTransport`.

## 10. Evaluación

```powershell
python -m scripts.evaluar_retrieval   # léxica vs vectorial vs híbrida
python -m scripts.evaluar_rag         # extremo a extremo, 12 casos
```

Los informes van a `docs/evaluacion_retrieval.json` y `docs/evaluacion_rag.json`.

Miden propiedades verificables del sistema: grounding (cada fundamento apunta a una
norma recuperada y activa), literalidad de las citas, abstención en los casos que
deben abstenerse, y latencias. **No miden corrección jurídica**: no existe un
conjunto de respuestas legales validadas por un profesional, así que no se reporta
Recall@K ni precisión legal, porque no habría contra qué compararlos.

## 11. Degradación sin IA

Con Ollama apagado o `IA_ENABLED=false` siguen funcionando login, normativa,
documentos, clasificación, extracción, riesgos, comparación e historial. La búsqueda
híbrida cae a léxica y lo informa. Las funciones que requieren el modelo devuelven un
error seguro con su motivo, sin tumbar el backend.

## 12. Rendimiento

Medido en Ryzen 5 3600, 16 GB RAM, Radeon RX 5600 XT 6 GB, con Vulkan y reparto
GPU/CPU. El encoder corre en CPU (`EMBEDDING_NUM_GPU=0`) para dejarle la VRAM al
generativo. Los números reales de la última corrida están en
`docs/evaluacion_rag.json` y en `docs/ENTREGA_IA_LOCAL.md`.

Para que el modelo no se ahogue: no se envía el Código Civil completo, solo Top K;
los prompts son compactos; las fuentes no se repiten; las cláusulas de un contrato
se recortan antes de entrar al prompt y el presupuesto de contexto nunca corta el
texto de una norma a la mitad (si no entra, la fuente se omite y queda registrado).

## 13. Troubleshooting

- **`no_configurada`**: guardar `DATABASE_URL` en `.env`, en el directorio del backend.
- **Modelo ausente**: revisar `OLLAMA_MODELS` del *servidor* y `ollama list`.
- **Servicio no disponible**: `ollama serve`; comprobar el puerto 11434.
- **Timeout**: ajustar `OLLAMA_TIMEOUT`. No cambiar de modelo ni activar servicios
  externos para "arreglarlo".
- **`El servicio local de IA devolvió una respuesta que no pudo validarse`**: el
  modelo no respetó las reglas de citación dos veces seguidas. Es el comportamiento
  correcto: no se muestra nada sin verificar. El motivo interno queda en la
  trazabilidad de la consulta (`validacion_motivo`).
- **Búsqueda híbrida que responde "se utilizó la búsqueda léxica"**: faltan
  embeddings o el modelo de embeddings no coincide con el índice. Ejecutar
  `python -m scripts.generar_embeddings` y revisar el recuento que informa.
- **Dimensión distinta de 1024**: se cambió el modelo de embeddings. Hay que
  reindexar; el sistema no mezcla vectores de modelos distintos.

## 14. Instalar en otra PC

1. Instalar Python 3.13, Node.js y Ollama.
2. `ollama pull qwen3:8b` y `ollama pull qwen3-embedding:0.6b`.
3. Clonar el repositorio. No contiene modelos ni `.env`.
4. Crear `.env` desde `.env.example` con la `DATABASE_URL` y el `JWT_SECRET` propios.
5. `pip install -r requirements.txt`, `alembic upgrade head`.
6. `python -m scripts.generar_embeddings` (la primera vez indexa todo el corpus).
7. `python -m scripts.diagnosticar_ia` para confirmar el entorno.

No hay rutas absolutas en el código: todo se resuelve por variables de entorno.

El paso 2 es opcional si esa PC va a consultarle la IA a otra máquina del equipo en vez de
correr su propio modelo: ver §15.

## 15. Servir la IA al equipo por un túnel

El backend publicado en Azure no tiene GPU. La inferencia puede venir de una PC del equipo,
exponiendo **solo Ollama** detrás de un túnel de Cloudflare con autenticación.

```
App (Vercel)  ->  API (Azure)  ->  https://ia.<dominio>  ->  cloudflared  ->  127.0.0.1:11434
```

### Por qué un túnel y no abrir el puerto

Ollama **no tiene autenticación propia**: cualquiera que llegue a su puerto puede usar la GPU,
cargar modelos o borrar los que estén instalados. Por eso el backend valida el destino
(`app/core/ollama_destino.py`) y solo acepta dos formas: loopback sobre `http`, o remoto sobre
`https` **con** las credenciales. El túnel además sale hacia afuera, así que no hace falta IP
pública, ni reenvío de puertos, ni tocar el firewall, y funciona detrás de CGNAT.

### Alta, una sola vez

1. **Namecheap** (lo hace quien sea dueño del dominio): dos registros `NS` para el host `ia`,
   apuntando a los nameservers que dé Cloudflare. No afecta al resto del dominio.
2. **Cloudflare** (plan Free): agregar `ia.<dominio>` como zona propia.
3. **Zero Trust → Networks → Tunnels**: crear el túnel, instalar `cloudflared` en la PC con GPU
   y agregar un *public hostname* `ia.<dominio>` → `HTTP` → `127.0.0.1:11434`.
4. **Zero Trust → Access → Service auth**: crear un *service token*. El secreto se muestra
   una sola vez.
5. **Zero Trust → Access → Applications**: aplicación *self-hosted* sobre ese hostname, con una
   única política de acción **Service Auth**. Sin políticas `Allow` para navegadores.

Comprobación, antes de tocar el backend:

```bash
curl https://ia.<dominio>/api/tags \
  -H "CF-Access-Client-Id: <id>" -H "CF-Access-Client-Secret: <secret>"
curl -s -o /dev/null -w "%{http_code}\n" https://ia.<dominio>/api/tags   # sin token: 302 o 403
```

### Operación diaria

Quien sirve la IA:

```powershell
.\scripts\servir_ia.ps1 -Tunel <nombre-del-tunel> -Hostname ia.<dominio>
```

Quien la consulta cambia **una sola variable**. El token se deja puesto de forma permanente en
el `.env`, porque `Settings.ollama_cabeceras` devuelve `{}` cuando la URL es loopback:

```bash
OLLAMA_URL=http://127.0.0.1:11434      # mi propio Ollama
OLLAMA_URL=https://ia.<dominio>        # la PC con GPU del equipo
```

`python -m scripts.diagnosticar_ia` confirma cuál de los dos está respondiendo.

### El techo de 100 segundos

El plan gratis de Cloudflare devuelve 524 si el origen no empieza a responder en 100 s, y
`OllamaClient.generar` **no usa streaming**: espera la respuesta completa. La consulta normal
promedia 34,2 s con `rag_top_k=3` (§12), así que entra con margen. Lo que no entra es
`rag.responder_caso_complejo`, que pide hasta 600 s: ese flujo queda para uso local.

Por eso con el túnel se configura `OLLAMA_TIMEOUT=95`, para que corte el cliente y no
Cloudflare: el error sale como `IANoDisponible` y no como un 524 sin explicación.

Meter streaming en `generar()` sacaría el techo, pero toca salida estructurada con schema,
validación y conteo de tokens. Está anotado como trabajo pendiente en el `ADR-011`.

### Si la PC que sirve se apaga

No se rompe nada: es exactamente lo descrito en §11. El fallo de conexión se traduce a
`IANoDisponible` y la consulta responde con el respaldo léxico sobre la normativa, citando
fuentes igual (HU-05).

### Cachés de chequeo previo

Una consulta hacía 5 peticiones HTTP a Ollama y 3 eran chequeos repetidos (`/api/tags` y dos
`/api/show`). En loopback no se notaban; por el túnel eran 3 viajes de red por consulta. Ahora
se memorizan en `app/services/ia/cache_modelos.py` durante `OLLAMA_PREFLIGHT_TTL` segundos
(300 por defecto, `0` desactiva). Solo se cachean los chequeos exitosos: un fallo no queda
guardado, así el sistema se recupera apenas la PC vuelve, sin esperar el vencimiento.
`scripts/diagnosticar_ia.py` no usa el caché, porque existe para reportar el estado real.

## Pendiente: el warm-up debe usar el contexto del flujo complejo

`scripts/warmup_ia.py` carga `qwen3:8b` con `OLLAMA_NUM_CTX=4096`. El flujo de casos
complejos (`rag.responder_caso_complejo`) pide `num_ctx=16384` en la llamada de análisis,
porque lleva hasta 24 fuentes fragmentadas y genera una salida larga. Ollama trata un
cambio de `num_ctx` como un modelo distinto y lo **recarga** (~76 s medidos): la primera
consulta compleja después del warm-up paga esa recarga, y la descomposición (4096) y el
análisis (16384) también se alternan entre sí.

Qué hacer más adelante (no se toca todavía, a propósito): que el warm-up cargue con el
mismo `num_ctx` que el análisis, y evaluar si la descomposición y la revisión conviene
que usen esa misma ventana para no provocar recargas intermedias. Es una decisión de
rendimiento y se resuelve junto con la migración al hardware nuevo, no en la etapa de
calidad.
