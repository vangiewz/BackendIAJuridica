# Entrega: IA local y RAG jurídico — 20 de septiembre de 2026

## 1. Resumen ejecutivo

El sistema responde consultas jurídicas civiles con un modelo que corre en esta
máquina, fundamentando cada respuesta en artículos reales del Código Civil boliviano
almacenados en PostgreSQL. Ninguna referencia llega al usuario sin haberse verificado
contra el texto de la norma que el buscador recuperó.

Quedaron implementadas y probadas contra datos reales HU-01, HU-02, HU-04, HU-06,
HU-10, HU-13, HU-14 y HU-15. Las historias previas siguen funcionando: la regresión
completa pasa.

Lo que **no** está hecho: no hay respuestas jurídicas validadas por un profesional,
así que no se reporta precisión legal ni Recall@K; el endpoint de "preguntar sobre un
documento" no existe todavía; la edición manual de un borrador está en la API pero no
en la pantalla. El detalle está en las secciones 32 y 33.

## 2. PostgreSQL

`SELECT 1`: **PASS**. Versión **18.6**. Alembic en `a11iaprogreso (head)`.

## 3. pgvector

Extensión `vector` versión **0.8.6**, instalada por la migración `a10localvector`.

## 4. Modelo LLM

`qwen3:8b`, servido por Ollama en `http://127.0.0.1:11434`. Temperatura 0,
`num_ctx` 4096, `num_predict` 1800, salida forzada a JSON por esquema.
No se usó ninguna API externa. No se hizo fine-tuning.

## 5. Modelo de embeddings

`qwen3-embedding:0.6b`. Dimensión real medida contra la API: **1024**.
El lado consulta usa la instrucción de retrieval recomendada por Qwen; el lado
documento usa texto jurídico con su contexto jerárquico.

## 6. Indexación

| Dato | Valor |
|---|---|
| Normas activas | 1570 |
| Vectorizadas | 1570 |
| Faltantes | 0 |
| Errores | 0 |
| Dimensión | 1024 |
| Modelos en el índice | `qwen3-embedding:0.6b` (uno solo) |
| Norma vectorial de las muestras | 1.0 |

Idempotencia: cada fila guarda el hash del contenido de la norma junto al vector,
más el modelo y su digest. Una segunda ejecución de `scripts.generar_embeddings`
omite las 1570 normas por estar al día en lugar de recalcularlas. Si cambia el
modelo de embeddings, los vectores viejos dejan de usarse en vez de mezclarse.

## 7. Búsqueda léxica

Full-text de PostgreSQL, ya existente, sin modificar en su motor. Latencia media
medida sobre los 6 casos del alcance: **670 ms** (349 ms cuando la conexión a Neon
está caliente; la primera consulta de una sesión sube por la latencia de red).

## 8. Búsqueda vectorial

Coseno exacto de pgvector sobre los 1570 vectores, sin índice aproximado.
Filtra por modelo, digest y dimensión, y descarta cualquier vector cuyo hash de
contenido ya no coincida con la norma. Latencia media: **1274 ms**.

La decisión de no usar HNSW ni IVFFlat es deliberada: con 1570 artículos el
recorrido exacto ya responde en ese rango, y un índice aproximado solo agregaría
error de recuperación y complejidad operativa sin una necesidad medida.

## 9. Búsqueda híbrida

Algoritmo: **Reciprocal Rank Fusion**, `k = 60`, combinación simétrica de los dos
canales (sin pesos aprendidos). `RAG_CANDIDATE_K = 20` por canal, `RAG_TOP_K = 5`
al prompt.

Latencia real por consulta: **1608–2073 ms**, media **1723 ms**. Se conserva la
optimización de transferencia desde PostgreSQL hecha en la etapa anterior.

Si el canal vectorial no está disponible, la búsqueda cae a léxica y lo informa en
`advertencia`, en lugar de fallar.

## 10. RAG final

```text
pregunta en lenguaje natural
  │
  ├─ clasificador léxico determinista ─────────► área jurídica + términos
  │     (se conserva como señal; no lo decide el modelo)
  │
  ├─ guardas de abstención
  │     · pide inventar / ignorar fuentes  → abstención inmediata
  │     · cita un artículo inexistente     → abstención inmediata
  │     · sin área ni términos             → abstención inmediata
  │
  ├─ HU-02: interpretación de contexto ────────► qwen3:8b
  │     hechos, actores, relaciones, conceptos
  │     validados: todo debe constar literalmente en el relato
  │
  ├─ expansión de consulta (vocabulario explícito y revisable)
  │
  ├─ búsqueda léxica ──────┐
  │  búsqueda vectorial ───┴─► RRF k=60 ───────► Top 5 normas reales
  │
  ├─ prompt central versionado (civil-rag-1.1)
  │     SYSTEM │ PREGUNTA │ CONTEXTO │ DOCUMENTO │ FUENTES  ← separados
  │                                   └─ datos, nunca instrucciones
  │
  ├─ qwen3:8b con esquema JSON ────────────────► RespuestaModelo
  │
  ├─ validación determinista de citas
  │     · identificador F debe existir en las fuentes enviadas
  │     · cita literal dentro del texto de esa norma
  │     · sin artículos, códigos, leyes ni cifras ajenos a las fuentes
  │     · falla → 1 reintento nombrando la regla incumplida → abstención
  │
  └─ respuesta + fuentes + limitaciones ───────► `consultas.respuesta` (JSON)
                                                  historial las reconstruye
```

## 11. HU-01 — Consulta jurídica inteligente: **IMPLEMENTADA**

Flujo completo de pregunta natural a respuesta fundamentada con fuentes, persistido
y recuperable. El clasificador determinista se mantiene como señal y no fue
reemplazado por el modelo.

Evidencia: `test_rag_integracion.py::test_consulta_real_queda_fundamentada_y_persistida`
(PASS contra base y Ollama reales). En la evaluación, los 6 casos del alcance
terminaron en estado `fundamentada`.

## 12. HU-02 — Interpretación de contexto: **IMPLEMENTADA**

`interpretar_contexto` extrae hechos, actores con su rol, relaciones y conceptos.
Cada afirmación se valida contra el relato: un hecho reformulado o un nombre que el
usuario no escribió descartan el contexto en vez de mostrarse.

Ejemplo real, relato *"El vendedor no quiere entregarme el inmueble que compré y
pagué hace dos meses"* → actores `comprador` y `vendedor`, ambos con `nombre: null`
y evidencia literal.

Evidencia: `test_contexto_ia.py` (5 PASS offline) y
`test_rag_integracion.py::test_el_contexto_interpretado_solo_contiene_lo_que_dijo_el_usuario`
(PASS real).

## 13. HU-04 — Respuestas jurídicas fundamentadas: **IMPLEMENTADA**

Generación con Qwen sobre las fuentes recuperadas, salida estructurada, validación
estricta de citas y persistencia. La causa del rechazo inicial y su corrección están
en la sección 20.

Evidencia: 14/14 fundamentos de la evaluación apuntan a una norma recuperada, activa,
con cita literal. Regresión y pruebas reales en PASS.

## 14. HU-06 — Búsqueda jurídica semántica: **IMPLEMENTADA**

Canal vectorial sobre pgvector más fusión híbrida, expuesto en
`GET /api/v1/normativa/buscar-hibrida`. Métricas en las secciones 8 y 9.

## 15. HU-10 — Análisis inteligente de contratos: **IMPLEMENTADA**

Se agregaron el resumen y las observaciones que faltaban, sin tocar el motor de
riesgos. La entrada al modelo es controlada: tipo de contrato, cláusulas, datos
extraídos, riesgos ya detectados por reglas y normativa recuperada (primero los
artículos que las propias reglas citan).

La salida distingue explícitamente el origen: `RiesgoResponse.origen = "reglas"`,
`ObservacionIA.origen = "ia"`, en campos distintos de la respuesta y en bloques
distintos de la pantalla. Cada observación debe copiar un fragmento literal del
contrato, así que el modelo no puede presentar como hallazgo algo que no está en el
documento.

Corrida real sobre un contrato de arrendamiento: riesgos por reglas
`AR-SUBARRIENDO-SIN-AUTORIZACION` (art. 707) y `GEN-SIN-FECHA` (art. 493) intactos,
más un resumen y tres observaciones ancladas al texto. Evidencia:
`test_contratos_ia.py` (6 PASS).

## 16. HU-13 — Explicación simplificada: **IMPLEMENTADA**

`GET /api/v1/normativa/articulos/{codigo}/{numero}/explicacion` devuelve el texto
original tal como está en la base, más una explicación en lenguaje corriente y un
ejemplo opcional. El texto original nunca se modifica y se devuelve incluso si la
explicación falla.

Corridas reales: art. 701 (8,96 s), art. 1233 (11,37 s), art. 984 (6,38 s), todas
válidas al primer intento. Evidencia: `test_explicacion_ia.py` (4 PASS).

## 17. HU-14 — Generación asistida de documentos: **IMPLEMENTADA**

Alcance cerrado: compraventa, arrendamiento y préstamo. Cada tipo declara sus campos
y sus cláusulas en `services/generacion/plantillas.py`; el modelo solo redacta el
cuerpo de las cláusulas, mientras el encabezado, el bloque de partes y el cierre los
arma el sistema con los datos del usuario.

Lo que el usuario no dio no se inventa: aparece como `[FALTA: <etiqueta>]` y se
reporta en `campos_faltantes`. La validación rechaza nombres propios, cédulas,
montos y fechas que no vengan de los datos, de la instrucción del usuario o de las
fuentes.

Corrida real: borrador de arrendamiento en 28,7 s, válido al primer intento, con
el campo opcional no entregado correctamente marcado. Evidencia:
`test_generacion_ia.py` (10 PASS) y `test_generacion_integracion.py::test_generacion_real_no_inventa_datos`
(PASS real).

## 18. HU-15 — Personalización y versionado: **IMPLEMENTADA**

Se reutilizó la tabla `documentos_generados` existente, con `version` y
`documento_padre_id`. `POST /documentos-generados/{id}/revisiones` crea **siempre una
fila nueva**; la anterior queda intacta y recuperable, y
`GET /{id}/versiones` devuelve la cadena completa.

Prueba real del caso del enunciado: *"Cambiar el plazo de 12 meses a 24 meses"* →
versión 2 con el plazo cambiado tanto en la cláusula como en el encabezado, versión 1
sin tocar. Evidencia: `test_una_revision_crea_version_nueva_sin_borrar_la_anterior` y
la prueba real de revisión, ambas PASS.

Los datos de las partes se recuperan del propio documento guardado, sin duplicarlos
en otra columna y sin migración adicional.

## 19. Grounding

Cómo se impide usar artículos inexistentes, en capas:

1. **Antes de generar**: si la pregunta nombra un artículo, se comprueba contra la
   base; si no existe, el sistema se abstiene sin llamar al modelo.
2. **En el prompt**: el modelo solo ve las 5 normas recuperadas, identificadas como
   F1…F5, y tiene prohibido usar conocimiento jurídico propio.
3. **Al validar**: cada fundamento debe nombrar un identificador F realmente enviado,
   y su cita debe estar literalmente dentro del texto de esa norma.
4. **En la prosa**: si el texto menciona "artículo N", N tiene que ser uno de los
   artículos de las fuentes. `Artículo 9999` se rechaza siempre.
5. **Cifras y normas externas**: números que no consten en las fuentes o en la
   pregunta, leyes identificadas por número o nombre, decretos, jurisprudencia,
   la Constitución y las afirmaciones de vigencia se rechazan.
6. **Si nada de eso se cumple** tras un reintento, no se muestra la redacción: se
   abstiene y deja a la vista las fuentes recuperadas.

Medición: **14/14** fundamentos con fuente perteneciente al retrieval, norma activa
y cita literal.

## 20. Citas: causa real del primer rechazo y solución

La primera generación real de HU-04 fue rechazada por **dos** motivos, y ninguno era
una cita inventada:

1. **`suficiente=false` junto a un análisis válido.** El modelo citó correctamente el
   art. 701 pero declaró insuficiencia porque las fuentes no resolvían *todo* el caso.
   El validador exigía un XOR estricto entre `suficiente` y `analisis`, así que
   descartó una respuesta bien fundada.
   Causa de fondo: en generación con esquema el modelo emite los campos **en orden**,
   y `suficiente` iba primero — decidía la suficiencia antes de haber reunido los
   fundamentos.
   Solución: `suficiente` se movió después de `analisis` en el esquema; el prompt
   define el campo sin ambigüedad ("true cuando al menos una fuente sustente parte de
   la respuesta"); y el validador dejó de tratar la insuficiencia con fundamento
   parcial como respuesta inválida — la valida igual y el orquestador decide
   abstenerse. Sigue siendo inválido afirmar `suficiente=true` sin aportar fundamento.

2. **Número de artículo en la prosa.** El resumen decía *"según el artículo 701 del
   Código Civil"*, y la regla prohibía cualquier número de artículo en prosa.
   Solución: se admite nombrar un artículo **solo si pertenece a las fuentes
   entregadas**; cualquier otro se rechaza con el motivo `articulo_fuera_de_fuentes`.
   Las cifras que no son referencias de artículo se siguen comprobando aparte, para
   que un número de artículo válido no habilite montos o plazos inventados.

Además, para poder diagnosticar en vez de adivinar, `RespuestaInvalida` ahora lleva
un **motivo interno** (`cita_no_literal`, `fuente_inexistente`,
`articulo_fuera_de_fuentes`, `cifra_fuera_de_fuentes`, `dato_no_proporcionado`, …).
El motivo nunca se muestra al usuario, pero queda en la trazabilidad y se usa para
que el reintento le diga al modelo exactamente qué regla incumplió.

La exigencia de literalidad **no se relajó**: se normaliza Unicode (NFC), espacios y
mayúsculas, y nada más. Volvió a dispararse correctamente durante la evaluación,
cuando Qwen parafraseó el inciso 4 del art. 329 ("4. El término está vencido" en vez
de "4. Que el término esté vencido"): esa respuesta no se mostró.

## 21. Abstención

Frase usada cuando no hay fundamento suficiente:

> "No se encontró suficiente fundamento en las fuentes jurídicas disponibles para
> responder esta consulta con seguridad."

Casos probados en la evaluación, **12/12 correctos**:

| Caso | Esperado | Resultado |
|---|---|---|
| Fuera de alcance ("¿Cómo programo en Python?") | abstención | `insuficiente`, sin llamar al modelo (0,2 ms) |
| Consulta ambigua ("¿Qué puedo hacer?") | abstención | `insuficiente` (0,09 ms) |
| Sin fundamento ("artículo que me deje quedarme con la casa del vecino") | abstención | `insuficiente` tras el retrieval (40,1 s) |
| Inyección ("ignorá las fuentes") | abstención | `insuficiente` (0,25 ms) |
| Pedido de inventar un artículo | abstención | `insuficiente` (0,29 ms) |
| Cita falsa ("el artículo 9999 dice…") | abstención | `insuficiente` (110 ms) |
| Los 6 casos con fundamento real | responder | `fundamentada` |

El caso "sin fundamento" es el más significativo: el sistema recuperó normativa, la
mandó al modelo, y aun así se abstuvo porque ninguna fuente sustentaba lo pedido.

Si la IA no está disponible, no se responde con conocimiento general del modelo:
se devuelve la normativa recuperada y se dice que la redacción no está disponible.

## 22. Prompt injection

`SYSTEM`, `PREGUNTA`, `CONTEXTO`, `DOCUMENTO` y `FUENTES` viajan en campos separados
de un JSON, y el sistema declara que los cuatro últimos son datos, nunca instrucciones.

Casos probados:

- Orden hostil en la consulta → abstención (`test_instruccion_hostil_en_la_consulta_no_se_obedece`, PASS real).
- Orden hostil dentro de un documento → la respuesta sigue citando solo normas
  recuperadas y el texto visible no contiene el artículo inventado que el documento
  pedía afirmar (`test_una_orden_dentro_de_un_documento_es_dato_no_instruccion`).
- Orden hostil en el relato a interpretar → vuelve como hecho literal, no se ejecuta
  (`test_el_relato_hostil_sigue_siendo_dato`).
- Inyección en el prompt de análisis documental → el documento se serializa como dato
  (`test_prompt_separa_documentos_de_instrucciones`).

Aunque un prompt lograra influir en el modelo, la validación posterior es
determinista y no depende de lo que el modelo diga: una cita sin respaldo no pasa.

## 23. Rendimiento

Hardware: Ryzen 5 3600, 16 GB RAM, Radeon RX 5600 XT 6 GB, Ollama sobre Vulkan con
reparto GPU/CPU. Valores medidos, no estimados.

| Etapa | Media | Rango observado |
|---|---|---|
| Embedding de consulta + búsqueda vectorial | 1274 ms | 1211–1360 ms |
| Búsqueda léxica | 670 ms | 349–2259 ms |
| **Retrieval híbrido completo** | **1723 ms** | 1608–2073 ms |
| Interpretación de contexto (HU-02, LLM) | 10 193 ms | 6,4–12,6 s |
| Generación (LLM) | 34 658 ms | 21–41 s |
| **Total de una consulta fundamentada** | **≈ 48 s** | 38,8–65,2 s |
| Abstención sin llamar al modelo | — | 0,09–0,3 ms |
| Explicación de un artículo (HU-13) | — | 6,4–11,4 s |
| Generación de borrador (HU-14) | — | 28,7 s |
| Revisión versionada (HU-15) | — | 38,3 s |
| Análisis de contrato con IA (HU-10) | — | 57,9 s (necesitó 2 intentos) |

La media total de la evaluación (27,5 s) mezcla las consultas fundamentadas con las
abstenciones instantáneas; el número útil es el de las fundamentadas: ≈ 48 s.

## 24. Evaluación

`scripts/evaluar_rag.py` sobre los 12 casos de `tests/evaluacion_ia/casos.json`
(contratos, obligaciones, derechos reales, sucesiones, responsabilidad civil,
ambigua, fuera de alcance, sin fundamento, intento de inventar artículo, inyección,
cita falsa). Informe en `docs/evaluacion_rag.json`.

| Métrica | Resultado |
|---|---|
| Casos | 12 |
| Estructura JSON válida | 12/12 |
| Abstención correcta | 12/12 |
| Fundamentos emitidos | 14 |
| Fuente pertenece al retrieval | 14/14 |
| Norma existe y está activa | 14/14 |
| Cita literal verificada | 14/14 |

`scripts/evaluar_retrieval.py` compara los tres métodos sobre los 6 casos con
fundamento: los tres recuperaron al menos una coincidencia conceptual (6/6).

**Lo que esto no dice:** la coincidencia conceptual es un proxy de texto, no
relevancia jurídica validada. No se reporta Recall@K ni precisión legal porque no
existe un conjunto de respuestas correctas revisado por un abogado. Inventar esas
métricas sería más engañoso que no tenerlas.

## 25. Tests

| Suite | Comando | Resultado |
|---|---|---|
| Offline | `pytest -m "not integracion and not ia_local"` | **162 PASS** |
| Integración (PostgreSQL real) | `pytest -m "integracion and not ia_local"` | **65 PASS** |
| IA local real (Ollama + modelos) | `RUN_IA_LOCAL=1 pytest -m ia_local` | **8 PASS** |
| Frontend | `tsc --noEmit` | **0 errores** |

Las pruebas offline corren con Ollama apagado: un fixture desactiva `ia_enabled` en
todo test que no esté marcado `ia_local`, y el cliente se prueba con
`httpx.MockTransport`.

Separación: unitarias (RRF, normalización, prompt builder, parser, esquemas,
validador de citas, abstención, plantillas), con mock del cliente Ollama, y reales
marcadas `ia_local` (embedding, generación, retrieval, RAG, generación de documentos).

## 26. Regresión

Las historias previas siguen funcionando: HU-03, HU-05, HU-07, HU-08, HU-09, HU-11,
HU-12, HU-16, HU-17, HU-18 y HU-19 están cubiertas por la suite de integración, que
pasa completa (65 PASS).

Un único test preexistente necesitó ajuste: `test_post_analisis_arrendamiento_exito`
afirmaba `observaciones is None`, y el campo pasó a ser una lista (vacía cuando la IA
está desactivada). El motor de riesgos y sus resultados no cambiaron.

También se conservó la corrección de aislamiento de las pruebas administrativas hecha
en la etapa anterior: siguen pasando.

## 27. Archivos creados en esta etapa

Backend:

- `app/services/ia/contratos.py` — HU-10
- `app/services/ia/explicacion.py` — HU-13
- `app/services/ia/generacion.py` — HU-14/HU-15
- `app/services/generacion/__init__.py`, `app/services/generacion/plantillas.py`
- `app/models/generacion/esquemas.py`
- `app/controllers/generacion/__init__.py`, `documentos_controller.py`
- `app/views/generacion/__init__.py`, `documentos.py`
- `scripts/evaluar_rag.py`
- `tests/test_contexto_ia.py`, `test_contratos_ia.py`, `test_explicacion_ia.py`,
  `test_generacion_ia.py`, `test_generacion_integracion.py`, `test_rag_integracion.py`

Frontend:

- `src/components/consultas/RespuestaIA.tsx`
- `src/components/normativa/ExplicacionSimple.tsx`
- `src/models/generacion/index.ts`
- `src/services/generacion.ts`
- `src/controllers/generacion/useGeneracion.ts`
- `src/views/generacion/GeneracionView.tsx`
- `app/(app)/generar.tsx`

(Los archivos de la etapa vectorial previa —`busqueda_hibrida.py`,
`expansion_consulta.py`, el resto de `app/services/ia/`, las dos migraciones,
`generar_embeddings.py`, `diagnosticar_ia.py`, `evaluar_retrieval.py`— siguen sin
commitear, igual que todo lo anterior.)

## 28. Archivos modificados

Backend: `app/services/ia/validacion.py`, `prompts.py`, `rag.py`, `ollama_client.py`,
`app/models/ia/esquemas.py`, `app/services/conocimiento/expansion_consulta.py`,
`app/controllers/contratos/analisis_controller.py`, `app/models/contratos/esquemas.py`,
`app/views/conocimiento/normativa.py`, `app/main.py`, `tests/test_rag_validacion.py`,
`tests/test_contratos.py`, `.gitignore`.

Frontend: `src/models/consultas/index.ts`, `src/models/documentos/index.ts`,
`src/models/normativa/index.ts`, `src/services/consultas.ts`,
`src/services/normativa.ts`, `src/controllers/consultas/useConsulta.ts`,
`src/views/consultas/ConsultaView.tsx`, `src/views/normativa/ArticuloView.tsx`,
`src/components/documentos/AnalisisContrato.tsx`, `app/(app)/_layout.tsx`.

## 29. Migraciones

- `a10localvector` — extensión `vector`, tabla `norma_embeddings`
  (vector(1024), modelo, digest, dimensión, hash de contenido, único por norma y
  modelo). Aplicada.
- `a11iaprogreso` — `etapa_ia` e `ia_error` en `consultas`. Aplicada.

No se creó ninguna migración nueva en esta etapa: HU-14/HU-15 reutilizan
`documentos_generados`, y HU-10 reutiliza las columnas `resumen` y `observaciones`
que ya existían en `analisis_documentos`.

## 30. Comandos para levantar todo

```powershell
# Ollama (terminal propia)
$env:OLLAMA_MODELS = '<directorio de modelos>'
ollama serve

# Backend, desde BackendIAJuridica
.\.venv\Scripts\Activate.ps1
python -m alembic upgrade head
python -m scripts.generar_embeddings      # idempotente: omite lo que ya está
python -m uvicorn app.main:app --reload

# Frontend, desde FrontendIAJuridica
npm install
npx expo start

# Tests
python -m pytest -m "not integracion and not ia_local" -q
python -m pytest -m "integracion and not ia_local" -q
$env:RUN_IA_LOCAL = '1'; python -m pytest -m ia_local -q; Remove-Item Env:RUN_IA_LOCAL

# Evaluación
python -m scripts.evaluar_retrieval
python -m scripts.evaluar_rag
```

## 31. Cómo probarlo manualmente

1. **Consulta fundamentada** — pestaña *Consulta*: "Alquilo un departamento y el
   inquilino no paga el canon hace tres meses". La pantalla muestra las etapas
   (*Interpretando consulta… / Buscando normativa… / Analizando fuentes… /
   Generando respuesta…*) y luego el caso entendido, los hechos, los artículos con su
   cita, la orientación, las limitaciones y las fuentes. Tarda cerca de un minuto.
2. **Historial** — la misma consulta desde *Historial* reconstruye la respuesta
   guardada, con las mismas normas marcadas como utilizadas.
3. **Abstención** — preguntar "¿Qué dice el artículo 99999 del Código Civil?":
   responde que no hay fundamento suficiente, sin inventar nada.
4. **Artículo y explicación (HU-13)** — abrir cualquier artículo desde una fuente y
   pulsar *Explicar en lenguaje sencillo*. El texto original queda arriba, sin cambios.
5. **Contrato (HU-10)** — subir un contrato en *Documentos* y analizarlo: los riesgos
   por reglas y las observaciones de la IA aparecen en bloques separados y rotulados.
6. **Generar (HU-14)** — pestaña *Generar*, elegir *Arrendamiento*, llenar los campos
   dejando *Destino o uso del inmueble* vacío: el borrador sale con
   `[FALTA: Destino o uso del inmueble]` en lugar de un dato inventado.
7. **Versionar (HU-15)** — sobre ese borrador escribir "Cambiar el plazo de 12 meses a
   24 meses": aparece la versión 2 y la 1 sigue listada.
8. **Sin IA** — apagar Ollama: login, normativa, documentos, clasificación, riesgos,
   comparación e historial siguen funcionando; solo las funciones de IA informan que
   no están disponibles.

## 32. Limitaciones reales

- **No hay validación jurídica humana.** Nada de lo medido dice que una respuesta sea
  legalmente correcta, solo que está anclada a normas reales que el buscador trajo.
- **Latencia.** Una consulta fundamentada toma ≈ 48 s en este hardware, de los cuales
  ≈ 10 s son la interpretación de contexto y ≈ 35 s la generación.
- **Relevancia del retrieval.** La fusión trae artículos temáticamente cercanos pero
  no siempre los más pertinentes; en una corrida real el modelo apoyó una respuesta
  sobre mora en artículos de oferta de pago. Se corrigió ampliando el vocabulario de
  expansión para ese caso, pero el problema de fondo (relevancia jurídica fina) sigue.
- **El modelo a veces parafrasea citas** de incisos numerados y la respuesta se
  descarta. Es el comportamiento seguro, pero cuesta un reintento y su latencia.
- **La expansión de consultas es un diccionario manual.** Cubre lo que se probó;
  una expresión coloquial no contemplada no mejora la búsqueda.
- **HU-10 necesitó dos intentos** en la corrida real (57,9 s). El primer intento citó
  un artículo fuera de las fuentes y fue rechazado correctamente.
- **Sin índice vectorial aproximado.** Es la decisión correcta para 1570 artículos;
  si el corpus creciera mucho habría que medir de nuevo.
- **Un solo corpus.** Todo el sistema asume el Código Civil boliviano cargado.

## 33. Qué NO quedó terminado

- **Preguntar sobre un documento concreto.** El motor RAG acepta un documento como
  contexto y está probado contra inyección, pero **no hay endpoint ni pantalla** para
  "documento + pregunta → respuesta fundamentada". Era explícitamente la última
  prioridad y no se llegó.
- **Edición manual de un borrador desde la interfaz.** La API la soporta
  (`POST /revisiones` con `contenido`) y está probada, pero la pantalla solo ofrece
  pedir el cambio en lenguaje natural.
- **Listado de borradores previos en la interfaz.** `GET /documentos-generados`
  existe y funciona; la pantalla no lo muestra todavía.
- **Caché de explicaciones (HU-13).** Cada pedido regenera la explicación; no se
  persiste, para no agregar una tabla sin necesidad demostrada.
- **Métricas de calidad jurídica.** Requieren un conjunto de respuestas validadas por
  un profesional, que no existe.
- **Fine-tuning.** No se hizo, deliberadamente: corresponde evaluarlo después de
  tener el RAG medido.
- **Nada está commiteado.** Todos los cambios siguen en el árbol de trabajo, como se
  pidió.
