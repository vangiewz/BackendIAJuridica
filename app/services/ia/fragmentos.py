"""Fragmentos contiguos para seleccionar citas sin pedir al modelo que las transcriba.

Se entrega TODO el artículo, en orden: concatenar los fragmentos reproduce el original.
La cita pública siempre se copia del corpus y pasa por validar_citas sin excepciones.
"""
import re
from app.models.ia.esquemas import RespuestaModelo
from app.services.ia.ollama_client import RespuestaInvalida


def fragmentar(texto):
    partes = []
    while len(texto) > 350:
        # Preferir fin de oración/inciso; conservar también el separador literal.
        finales = [m.end() for m in re.finditer(r"[.;]\s+|\n+", texto[:350]) if m.end() >= 40]
        corte = finales[-1] if finales else texto.rfind(" ", 40, 350) + 1
        corte = corte if corte >= 40 else 350
        partes.append(texto[:corte])
        texto = texto[corte:]
    if texto:
        if len(texto.strip()) < 12 and partes:
            partes[-1] += texto
        else:
            partes.append(texto)
    return partes


def resolver_citas(generado, fuentes):
    permitidas = {f"F{i}C{j}": (f"F{i}", texto) for i, fuente in enumerate(fuentes, 1)
                 for j, texto in enumerate(fragmentar(fuente.texto), 1)}
    analisis = []
    for item in generado.analisis:
        if item.cita_id not in permitidas:
            raise RespuestaInvalida("fuente_inexistente")
        fuente, literal = permitidas[item.cita_id]
        analisis.append({"fuente": fuente, "cita": literal, "explicacion": item.explicacion})
    return RespuestaModelo(resumen=generado.resumen, analisis=analisis,
        suficiente=generado.suficiente, conclusion=generado.conclusion,
        limitaciones=generado.limitaciones)


def resolver_citas_complejo(generado, fuentes):
    """Igual que `resolver_citas`, pero para un análisis dividido por problemas.

    El modelo eligió identificadores de fragmento; el texto de la cita lo copia el
    backend desde el corpus, nunca el modelo. Un problema puede quedarse sin citas
    —y entonces su explicación debe decir qué no pudo fundamentarse—, pero un
    identificador inexistente sigue invalidando la respuesta.
    """
    permitidas = {f"F{i}C{j}": (f"F{i}", texto) for i, fuente in enumerate(fuentes, 1)
                  for j, texto in enumerate(fragmentar(fuente.texto), 1)}
    analisis = []
    for orden, apartado in enumerate(generado.analisis):
        for cita_id in apartado.citas:
            if cita_id not in permitidas:
                exc = RespuestaInvalida("fuente_inexistente", cita_id)
                exc.apartado = apartado.problema
                exc.indice_apartado = orden
                exc.texto = apartado.explicacion
                exc.fuente = None
                exc.cita = None
                exc.cita_ids = list(apartado.citas)
                raise exc
            fuente, literal = permitidas[cita_id]
            # `apartado` identifica de qué apartado sale cada cita: dos apartados pueden
            # llegar con el mismo id de problema y no deben confundirse entre sí.
            analisis.append({"fuente": fuente, "cita": literal,
                             "explicacion": apartado.explicacion,
                             "problema": apartado.problema, "apartado": orden})
    return analisis
