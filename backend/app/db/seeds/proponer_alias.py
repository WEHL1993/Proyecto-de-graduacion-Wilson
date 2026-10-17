"""Propone equivalencias `alias -> sku` entre las ventas del Excel y el catálogo (M02, ADR-18).

Uso (desde `backend/`, con el venv activo):
    python -m app.db.seeds.proponer_alias --archivo "<VENTAS DIARIAS*.xlsx>"

Solo lee el libro y escribe un CSV de **revisión** en `data/reportes/`; no toca la BD ni crea
`data/plantillas/alias_excel.csv`. Las hojas de venta no traen código: identifican el producto
por `<medida>-<SABOR>` (p. ej. `3030-COLA`) y el catálogo por código + descripción. La propuesta
empata por medida (ml) y por las palabras del sabor; solo las filas de estado `unico` son
seguras, el resto requiere decisión humana. Se copian a `alias_excel.csv` (columnas `alias`,
`sku`) las filas aprobadas y se ejecuta el importador.
"""

import argparse
import csv
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import get_settings
from app.db.seeds.empate_alias import Candidato, Propuesta, proponer
from app.db.seeds.importar_catalogos import (
    Reporte,
    _abrir,
    clasificar_hojas,
    leer_claves_ventas,
    leer_productos,
)


def generar(archivo: Path) -> list[Propuesta]:
    reporte = Reporte()
    libro = _abrir(archivo)
    try:
        filas = leer_productos(libro, reporte)
        hojas = clasificar_hojas(libro, reporte)
        claves = leer_claves_ventas(libro, hojas)
    finally:
        libro.close()
    catalogo = [
        Candidato(
            f.sku, f.descripcion.nombre, f.descripcion.medida_ml, f.descripcion.unidades_por_paquete
        )
        for f in filas
    ]
    return [proponer(a, catalogo, ", ".join(sorted(h))) for a, h in sorted(claves.items())]


def escribir_csv(propuestas: list[Propuesta], carpeta: Path) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    marca = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    destino = carpeta / f"alias_propuesta_{marca}.csv"
    with destino.open("w", newline="", encoding="utf-8-sig") as fh:
        escritor = csv.writer(fh)
        escritor.writerow(["alias", "sku", "estado", "descripcion", "otros_candidatos", "hojas"])
        for p in propuestas:
            primero = p.candidatos[0] if p.candidatos else None
            escritor.writerow(
                [
                    p.alias,
                    primero.sku if primero and p.estado == "unico" else "",
                    p.estado,
                    primero.descripcion if primero else "",
                    " | ".join(f"{c.sku} {c.descripcion}" for c in p.candidatos[1:]),
                    p.hojas,
                ]
            )
    return destino


def main(argv: list[str] | None = None) -> int:
    datos = get_settings().data_dir
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--archivo", type=Path, required=True, help="Libro de ventas diarias.")
    parser.add_argument("--reportes", type=Path, default=datos / "reportes")
    args = parser.parse_args(argv)

    propuestas = generar(args.archivo)
    destino = escribir_csv(propuestas, args.reportes)
    resumen = {
        e: sum(p.estado == e for p in propuestas) for e in ("unico", "ambiguo", "sin_candidato")
    }
    print("=== Propuesta de alias ===")
    for estado, total in resumen.items():
        print(f"- {estado}: {total}")
    print(f"\nRevise y copie las filas aprobadas (alias, sku) a alias_excel.csv.\nCSV: {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
