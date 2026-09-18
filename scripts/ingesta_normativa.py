import argparse
import sys
from pathlib import Path
from sqlalchemy.orm import Session

from app.core.database import obtener_engine
from app.services.conocimiento.perfiles_fuente import CODIGO_CIVIL
from app.controllers.conocimiento.ingesta_controller import ingerir_fuente, ReporteIngesta
from app.controllers.conocimiento.errores import FuenteNoEncontradaError, CorpusIncompletoError

def _construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingesta normativa en base de datos.")
    parser.add_argument("--fuente", required=True, help="Clave de la fuente (ej. codigo_civil)")
    parser.add_argument("--dry-run", action="store_true", help="No escribe en base de datos")
    return parser

def _imprimir_reporte(reporte: ReporteIngesta) -> None:
    print(f"Reporte Ingesta - {reporte.codigo}")
    print(f"Total parseados: {reporte.total_parseados}")
    print(f"Insertadas:      {reporte.insertadas}")
    print(f"Actualizadas:    {reporte.actualizadas}")
    print(f"Sin cambios:     {reporte.sin_cambios}")
    print("Por Libro:")
    for libro, qty in reporte.por_libro.items():
        print(f"  {libro}: {qty}")
    print("Por Area:")
    for area, qty in reporte.por_area.items():
        print(f"  {area}: {qty}")

def main():
    parser = _construir_parser()
    args = parser.parse_args()

    if args.fuente != "codigo_civil":
        print(f"Fuente '{args.fuente}' no soportada.", file=sys.stderr)
        sys.exit(1)

    engine = obtener_engine()
    if not engine:
        print("Error: DATABASE_URL no configurada.", file=sys.stderr)
        sys.exit(1)

    try:
        with Session(engine) as db:
            reporte = ingerir_fuente(db, CODIGO_CIVIL, Path("data/normativa"))
            
            if args.dry_run:
                db.rollback()
                print("Modo dry-run: no se escribio nada en la base de datos.\n")
            else:
                db.commit()

            _imprimir_reporte(reporte)
            sys.exit(0)
    except (FuenteNoEncontradaError, CorpusIncompletoError) as e:
        print(f"Error de dominio: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error inesperado: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
