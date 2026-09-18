# Backend

## Local
1. Crear entorno virtual: `python -m venv .venv`
2. Activar entorno virtual
3. Instalar dependencias: `pip install -r requirements.txt`
4. Ejecutar: `uvicorn app.main:app --reload`

## Docker
Ejecutar: `docker compose up --build`

## Configuración y Variables de Entorno

Crear un archivo `.env` en la raíz de `Backend/` con las siguientes variables. (Nota: en desarrollo `JWT_SECRET` puede omitirse y se generará uno aleatorio, pero es obligatorio en producción).

| Variable | Descripción | Obligatoria | Ejemplo |
|---|---|---|---|
| `DATABASE_URL` | Cadena de conexión a PostgreSQL (Neon) | Sí | `postgresql+psycopg://user:pass@host/dbname?sslmode=require` |
| `ENVIRONMENT` | Entorno de ejecución (`development`, `production`) | No | `development` |
| `JWT_SECRET` | Clave secreta para firmar tokens JWT | Sí (excepto dev) | `super_secret_key_placeholder` |
| `JWT_ACCESS_MINUTOS` | Minutos de validez del access token | No (por defecto 30) | `30` |
| `JWT_REFRESH_DIAS` | Días de validez del refresh token | No (por defecto 7) | `7` |

## Migraciones de Base de Datos (Alembic)

Para aplicar las migraciones y crear las tablas (como `usuarios`), ejecuta:
`alembic upgrade head`

## Comandos

### Ingesta Normativa
Para sincronizar los artículos del Código Civil a la base de datos (parsea, ingiere y genera un reporte de manera idempotente):
```bash
python -m scripts.ingesta_normativa --fuente codigo_civil
```
Usa el flag `--dry-run` para parsear y armar el reporte sin escribir en la base de datos:
```bash
python -m scripts.ingesta_normativa --fuente codigo_civil --dry-run
```
