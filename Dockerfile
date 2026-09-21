FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Usuario no root
RUN useradd -m appuser
COPY --chown=appuser:appuser . .
USER appuser

# --proxy-headers: detras del balanceador de Azure la TLS termina afuera, y sin esto los
# redirects de FastAPI saldrian en http y el navegador los bloquearia por contenido mixto.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
