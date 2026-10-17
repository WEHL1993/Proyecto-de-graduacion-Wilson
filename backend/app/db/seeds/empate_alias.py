"""Empate automático `alias del Excel de ventas -> producto del catálogo` (M02, ADR-18).

Las hojas de venta no traen código: identifican el producto por `<medida>-<SABOR>`
(p. ej. `3030-COLA`) y el catálogo (`CODIGOS Y PRECIOS`) por código + descripción. El empate usa
la medida (ml) y las palabras del sabor, con una tabla de sinónimos para los errores de escritura
habituales del Excel. Solo un candidato único se considera seguro; lo demás se reporta.

Módulo puro: no toca la BD ni los libros, para poder usarse desde el importador y desde el
generador de propuestas sin importaciones circulares.
"""

from dataclasses import dataclass

from app.services.etl_lectura import normalizar_texto

# Palabras del Excel de ventas que no describen el sabor (empaque, formato).
_RUIDO = frozenset({"un", "uni", "unid", "unidad", "unidades", "caja", "pack", "pet"})
# Errores de escritura / abreviaturas del Excel -> palabras que deben aparecer en la descripción.
SINONIMOS: dict[str, tuple[str, ...]] = {
    "fruty": ("fruit", "punch"),
    "sporade": ("deporade",),
    "cifrus": ("cifrut",),
    "citrus": ("naranja", "mandarina", "limon"),
}
_LITRO_MAX = 100  # medidas menores se leen como litros (1.3 -> 1300 ml)

UNICO = "unico"
AMBIGUO = "ambiguo"
SIN_CANDIDATO = "sin_candidato"


@dataclass(frozen=True)
class Candidato:
    sku: str
    descripcion: str
    medida_ml: int | None
    unidades: int


@dataclass(frozen=True)
class Propuesta:
    alias: str
    estado: str  # unico | ambiguo | sin_candidato
    candidatos: tuple[Candidato, ...]
    hojas: str


def medida_y_palabras(alias: str) -> tuple[int | None, list[str], list[int]]:
    """Descompone `<medida>-<SABOR>`: medida en ml, palabras del sabor y números sueltos."""
    medida_txt, _, resto = alias.partition("-")
    medida: int | None = None
    if medida_txt != "SM":
        try:
            valor = float(medida_txt)
        except ValueError:
            return None, [], []
        medida = round(valor * 1000) if valor < _LITRO_MAX else round(valor)
    palabras: list[str] = []
    numeros: list[int] = []
    for pieza in normalizar_texto(resto).split("_"):
        if pieza.isdigit():
            numeros.append(int(pieza))
        elif pieza and pieza not in _RUIDO:
            palabras.extend(SINONIMOS.get(pieza, (pieza,)))
    return medida, palabras, numeros


def _contiene(descripcion: str, palabra: str) -> bool:
    """Palabra completa o, si es larga, dentro de una unida (`blue berry` ~ `blueberry`)."""
    normal = normalizar_texto(descripcion)
    return palabra in normal.split("_") or (
        len(palabra) >= 4 and palabra in normal.replace("_", "")
    )


def proponer(alias: str, catalogo: list[Candidato], hojas: str = "") -> Propuesta:
    medida, palabras, numeros = medida_y_palabras(alias)
    cercanos = [
        c
        for c in catalogo
        if (medida is None or c.medida_ml == medida)
        and all(_contiene(c.descripcion, p) for p in palabras)
    ]
    if len(cercanos) > 1 and numeros:  # «Cola 8 un»: el número desempata por unidades/paquete
        por_paquete = [c for c in cercanos if c.unidades in numeros]
        cercanos = por_paquete or cercanos
    estado = SIN_CANDIDATO if not cercanos else UNICO if len(cercanos) == 1 else AMBIGUO
    return Propuesta(alias, estado, tuple(cercanos), hojas)
