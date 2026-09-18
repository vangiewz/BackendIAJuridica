import re

# Bs. 1.500,00 · Bs1500 · Bs 1,500.00
MONTO_BOLIVIANOS: re.Pattern = re.compile(r'\bBs\.?\s*(?:\d{1,3}(?:[.,]\d{3})*|\d+)(?:[.,]\d{2})?\b', re.IGNORECASE)

# $us. 200 · $us200 · USD 200 · US$ 200
MONTO_DOLARES: re.Pattern = re.compile(r'(?:\$us\.?|USD|US\$)\s*(?:\d{1,3}(?:[.,]\d{3})*|\d+)(?:[.,]\d{2})?\b', re.IGNORECASE)

# 15/03/2024 · 15-03-2024 · 15.03.2024
FECHA_NUMERICA: re.Pattern = re.compile(r'\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}\b')

# 15 de marzo de 2024 · quince de marzo de 2024 (no)
FECHA_LARGA: re.Pattern = re.compile(r'\b\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+de\s+\d{4}\b', re.IGNORECASE)

# C.I. 1234567 · C.I. 1234567 L.P. · cedula de identidad No 1234567
CEDULA: re.Pattern = re.compile(r'(?:C\.?\s*I\.?|c[eé]dula\s+de\s+identidad(?:\s+N[oó]\.?)?)\s*\d{4,10}(?:\s+(?:L\.?P\.?|C\.?B\.?|S\.?C\.?|O\.?R\.?|P\.?T\.?|T\.?J\.?|C\.?H\.?|B\.?E\.?|P\.?D\.?)(?:-[A-Za-z0-9]+)?)?', re.IGNORECASE)

# NIT 1234567890
NIT: re.Pattern = re.compile(r'\bNIT\s*\d{8,15}\b', re.IGNORECASE)

# 30 dias · tres (3) meses · 2 años
PLAZO: re.Pattern = re.compile(r'\b(?:\d+|un|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|quince|veinte|treinta|cuarenta|cincuenta|sesenta|noventa|cien)(?:\s*\(\d+\))?\s+(?:d[ií]as?|mes(?:es)?|a[nñ]os?)\b', re.IGNORECASE)

# conste por el presente · intervienen · suscriben · celebran · por una parte
# NO incluye "entre" a secas: "entre otras cosas" aparece en cualquier parrafo y ganaba la
# carrera por ser el primero, devolviendo como parrafo de las partes uno que no lo era.
INICIO_PARTES: re.Pattern = re.compile(
    r'\b(?:conste\s+por\s+el\s+presente'
    r'|intervienen'
    r'|suscriben'
    r'|(?:que\s+)?celebran'
    r'|(?:de|por)\s+una\s+parte)\b',
    re.IGNORECASE,
)
