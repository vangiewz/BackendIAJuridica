"""Guía funcional de las pantallas autenticadas. Solo describe controles existentes."""
from app.services.generacion.plantillas import PLANTILLAS


PANTALLAS = {
    "asistente": {
        "titulo": "Asistente jurídico",
        "descripcion": "Permite consultar normativa o preguntar sobre un documento activo.",
        "pasos": ["Escribí una consulta o adjuntá un documento con el clip.",
                  "Enviá la pregunta y revisá la respuesta y sus fuentes."],
        "acciones": {
            "adjuntar": "El clip permite subir un archivo o elegir uno de tus documentos guardados.",
            "documento_activo": "La barra superior muestra el documento usado en las próximas preguntas.",
            "cambiar_documento": "Usá el icono de cambio junto al documento activo para elegir otro.",
            "quitar_documento": "Usá el icono de cierre para quitar el documento activo.",
            "guardar": "Guardar conserva el documento en tu cuenta; no ejecuta su análisis.",
            "analizar": "Analizar ejecuta el análisis documental cuando lo pedís expresamente.",
            "fuentes": "Las fuentes de la respuesta se abren desde el mensaje del asistente.",
        },
        "campos": {},
        "faq": [
            ("¿Cómo adjunto un documento?", "Tocá el clip junto al mensaje y elegí subir un archivo o usar uno guardado.", "adjuntar"),
            ("¿Qué diferencia hay entre guardar y analizar?", "Guardar conserva el documento. Analizar revisa su contenido y muestra resultados cuando lo pedís.", "guardar"),
            ("¿Cómo cambio el documento activo?", "En la barra del documento activo, tocá el icono de cambio y elegí otro documento.", "cambiar_documento"),
        ],
    },
    "generar": {
        "titulo": "Generar documento",
        "descripcion": "Crea un borrador de compraventa, arrendamiento o préstamo con una plantilla.",
        "pasos": ["Describí el documento y tocá Interpretar datos, o elegí un tipo y completá sus campos.",
                  "Revisá los datos detectados y los pendientes.",
                  "Tocá Generar borrador; después podés revisarlo y descargarlo."],
        "acciones": {
            "interpretar_datos": "Interpreta tu descripción inicial y propone tipo y datos editables.",
            "completar_campos": "Completar campos toma información adicional escrita en texto y llena los campos que reconoce.",
            "generar_borrador": "Genera el borrador del tipo seleccionado con los datos actuales; los vacíos quedan señalados.",
            "pendiente": "Pendiente indica un campo sin dato. En el borrador se marca como [FALTA: ...]; no se inventa un valor.",
            "descargar": "En la vista del borrador se ofrecen descargas Word y PDF en la versión web.",
        },
        "campos": {},
        "faq": [
            ("¿Cómo genero un documento?", "Elegí compraventa, arrendamiento o préstamo, completá o interpretá los datos y tocá Generar borrador. Revisá los pendientes antes de usarlo.", "generar_borrador"),
            ("¿Qué campos son obligatorios?", "Dependen de la plantilla elegida. Los opcionales están marcados como tales junto a su nombre; los demás figuran como obligatorios.", "generar_borrador"),
            ("¿Qué significa Pendiente?", "Es un dato que no completaste. El borrador lo marca como [FALTA: ...] y no lo inventa.", "pendiente"),
            ("¿Cómo completo datos mediante texto?", "Escribí información adicional en Completar datos mediante texto y tocá Completar campos. Revisá lo detectado antes de generar.", "completar_campos"),
        ],
    },
    "reportes": {
        "titulo": "Reportes dinámicos",
        "descripcion": "Genera reportes con una frase o con el constructor visual.",
        "pasos": ["Elegí Generar con IA o Constructor visual.",
                  "En el constructor, elegí información, columnas, ajustes opcionales y visualización.",
                  "Generá el reporte; la exportación aparece con el resultado."],
        "acciones": {
            "generar_ia": "Interpreta una descripción escrita y genera el reporte.",
            "constructor_visual": "Permite elegir datos y ajustes paso a paso.",
            "columnas": "Las columnas son los datos que aparecerán en el resultado.",
            "filtrar": "Filtrar muestra solo registros que cumplen una condición.",
            "agrupar": "Agrupar junta registros con un valor común, por ejemplo un resultado por tipo de documento.",
            "calculos": "Permite contar, sumar o calcular promedios, mínimos y máximos según los datos disponibles.",
            "ordenar": "Cambia el orden en que aparecen los resultados.",
            "visualizacion": "Permite mostrar los mismos datos como tabla, barras, torta o resumen si son compatibles.",
            "exportar": "Después de generar el reporte, el bloque Exportar ofrece PDF, Word, Excel y PowerPoint en web; también hay CSV en web.",
        },
        "campos": {},
        "faq": [
            ("¿Cómo creo un reporte?", "Describí el resultado y tocá Generar reporte, o abrí Constructor visual para elegir datos y ajustes paso a paso.", "generar_ia"),
            ("¿Qué significa agrupar?", "Agrupar junta resultados con un valor común. Por ejemplo, agrupar documentos por tipo da una fila por cada tipo.", "agrupar"),
            ("¿Cómo filtro resultados?", "En Constructor visual, abrí Filtrar, elegí un dato, una condición y el valor que querés mostrar.", "filtrar"),
            ("¿Cómo exporto a Excel?", "Generá el reporte y, en el resultado, tocá Excel dentro de Exportar. La descarga de archivos está disponible en web.", "exportar"),
        ],
    },
    "documentos": {
        "titulo": "Documentos",
        "descripcion": "Sube y analiza un documento jurídico; muestra datos extraídos y riesgos.",
        "pasos": ["Tocá Seleccionar documento y elegí un archivo admitido.",
                  "Tocá Analizar documento para subirlo y procesarlo.",
                  "Revisá la información extraída, el análisis y los riesgos."],
        "acciones": {
            "seleccionar": "Elige un archivo PDF, Word o texto de tu dispositivo.",
            "analizar": "Sube el archivo y ejecuta el análisis documental.",
            "riesgos": "Los riesgos detectados aparecen debajo del análisis cuando hay resultado.",
            "ver_guardados": "Los documentos procesados se pueden abrir desde Historial, pestaña Documentos.",
        },
        "campos": {},
        "faq": [
            ("¿Cómo analizo un documento?", "Tocá Seleccionar documento, elegí el archivo y después Analizar documento.", "analizar"),
            ("¿Cómo comparo documentos?", "Abrí Comparar, elegí dos documentos procesados y tocá Comparar documentos.", "comparaciones"),
            ("¿Dónde veo los riesgos?", "Después del análisis, bajá hasta Riesgos contractuales. También podés reabrir el documento desde Historial.", "riesgos"),
        ],
    },
    "comparaciones": {
        "titulo": "Comparar documentos",
        "descripcion": "Compara dos documentos procesados y muestra las diferencias.",
        "pasos": ["Procesá al menos dos documentos desde Documentos.",
                  "Elegí uno en cada lista y tocá Comparar documentos.",
                  "Revisá los cambios; el resultado también queda en Historial."],
        "acciones": {
            "elegir_documentos": "Selecciona dos documentos ya procesados.",
            "comparar": "Compara cláusulas reconocidas o párrafos y muestra diferencias.",
            "ver_historial": "Las comparaciones realizadas se pueden reabrir desde Historial.",
        },
        "campos": {},
        "faq": [("¿Cómo comparo dos contratos?", "Primero procesá ambos en Documentos. Luego elegí uno en cada lista de Comparar y tocá Comparar documentos.", "comparar")],
    },
    "historial": {
        "titulo": "Historial",
        "descripcion": "Muestra consultas, documentos procesados y comparaciones guardadas.",
        "pasos": ["Elegí la pestaña Consultas, Documentos o Comparaciones.",
                  "Tocá un elemento para abrir su detalle."],
        "acciones": {
            "consultas": "Abre consultas anteriores y sus respuestas.",
            "documentos": "Abre documentos procesados y sus análisis guardados.",
            "comparaciones": "Abre comparaciones realizadas anteriormente.",
        },
        "campos": {},
        "faq": [("¿Dónde veo mis documentos?", "Abrí Historial y elegí la pestaña Documentos. Tocá uno para ver su detalle.", "documentos")],
    },
    "general": {
        "titulo": "Ayuda de la aplicación",
        "descripcion": "Orientación para usar los módulos disponibles de la aplicación.",
        "pasos": ["Elegí una sección de la navegación para comenzar."],
        "acciones": {
            "asistente": "Consultas jurídicas y preguntas sobre documentos.",
            "documentos": "Carga y análisis de documentos.",
            "generar": "Generación de borradores.",
            "reportes": "Reportes dinámicos.",
            "comparaciones": "Comparación de documentos procesados.",
            "historial": "Consulta de resultados guardados.",
        },
        "campos": {},
        "faq": [],
    },
}

DESTINOS = frozenset(("asistente", "documentos", "generar", "reportes", "historial", "comparaciones"))
CAPACIDADES = {
    "asistente": ["hacer consultas jurídicas generales", "adjuntar un documento nuevo o elegir uno guardado",
                  "hacer preguntas sobre su contenido", "guardarlo o pedir su análisis",
                  "cambiar o quitar el documento activo", "consultar las fuentes de las respuestas"],
    "generar": ["elegir una plantilla de compraventa, arrendamiento o préstamo",
                "completar sus datos a mano o mediante texto", "revisar los campos pendientes",
                "generar un borrador y descargarlo en web"],
    "reportes": ["crear un reporte mediante una descripción o el constructor visual",
                 "elegir columnas, filtros, agrupaciones y cálculos", "revisar su visualización",
                 "exportar el resultado en web"],
    "documentos": ["seleccionar un archivo", "analizar su contenido", "revisar los datos extraídos y los riesgos",
                   "reabrir documentos procesados desde Historial"],
    "comparaciones": ["elegir dos documentos procesados", "comparar su contenido",
                      "revisar las diferencias y reabrir el resultado desde Historial"],
    "historial": ["consultar tus preguntas anteriores", "reabrir documentos procesados",
                  "ver comparaciones realizadas"],
    "general": ["elegir Asistente jurídico, Documentos, Generar, Reportes, Comparar o Historial en la navegación"],
}
BOTONES = {
    "asistente": {"adjuntar": "Clip para adjuntar documento", "cambiar_documento": "Cambiar documento activo"},
    "generar": {"interpretar_datos": "Interpretar datos", "completar_campos": "Completar campos",
                "generar_borrador": "Generar borrador"},
    "reportes": {"generar_ia": "Generar reporte", "constructor_visual": "Constructor visual",
                 "exportar": "Exportar"},
    "documentos": {"seleccionar": "Seleccionar documento", "analizar": "Analizar documento"},
    "comparaciones": {"comparar": "Comparar documentos"},
    "historial": {},
    "general": {},
}
DESTACADOS = {
    "prestamo": {"garantia", "interes", "plazo_devolucion"},
    "arrendamiento": {"canon", "plazo", "destino"},
    "compraventa": {"objeto", "forma_pago", "entrega"},
}
DESCRIPCIONES_CAMPOS = {
    "garantia": "Indicá la garantía ofrecida para este préstamo, si existe. No agregues una si no se pactó.",
    "interes": "Indicá el interés convenido, si existe; si no se acordó, dejá el campo vacío.",
    "plazo_devolucion": "Indicá el plazo o la fecha pactada para devolver el préstamo.",
    "canon": "Indicá el importe del alquiler y su moneda.",
    "plazo": "Indicá cuánto dura el arrendamiento según lo acordado.",
    "destino": "Indicá el uso acordado para el inmueble, si se definió.",
    "objeto": "Describí el bien que se vende de forma que pueda identificarse.",
    "forma_pago": "Indicá la forma y el plazo de pago convenidos.",
    "entrega": "Indicá cuándo y dónde se entregará el bien, si se acordó.",
}


def catalogo_para(pantalla: str, tipo_documento: str | None = None) -> dict:
    base = PANTALLAS[pantalla]
    campos = {}
    if pantalla == "generar" and tipo_documento:
        plantilla = next((p for tipo, p in PLANTILLAS.items()
                          if tipo.value == tipo_documento), None)
        if plantilla:
            campos = {campo.clave: {
                "etiqueta": campo.etiqueta,
                "descripcion": DESCRIPCIONES_CAMPOS.get(campo.clave,
                    f"Completá {campo.etiqueta.lower()} con el dato realmente acordado."),
                "obligatorio": campo.obligatorio,
                "destacado": campo.clave in DESTACADOS[tipo_documento],
            } for campo in plantilla.campos}
    return {**base, "id": pantalla, "capacidades": CAPACIDADES[pantalla],
            "botones": BOTONES[pantalla], "campos": campos,
            "faq": [{"pregunta": q, "respuesta": r, "referencia": ref}
                    for q, r, ref in base["faq"]],
            "sugerencias": [q for q, _, _ in base["faq"]]}
