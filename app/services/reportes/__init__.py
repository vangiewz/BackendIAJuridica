"""Reportes dinámicos: el usuario pide en lenguaje natural y el backend consulta.

El módulo es de solo lectura. El modelo de lenguaje únicamente traduce la petición a una
especificación estructurada; todo lo que toca la base se construye aquí con SQLAlchemy
sobre el catálogo de `catalogo.py`.
"""
