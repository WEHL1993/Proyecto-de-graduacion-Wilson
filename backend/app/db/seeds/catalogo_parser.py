r"""Interpretación de las descripciones de producto de `CODIGOS Y PRECIOS` (M02, ADR-18).

Función pura y sin E/S: deduce medida (ml), unidades por paquete y sabor con reglas explícitas.
Nada se corrige en silencio: cada decisión no trivial se devuelve en `avisos` para el reporte.

Reglas
1. Se normalizan espacios y Unicode (NFC). `PI�A` (mojibake del Excel) se corrige a `PIÑA`
   y se avisa; cualquier otro carácter ilegible se conserva y se avisa.
2. Medida: primer `<número> <unidad>` con unidad ML, L/LT/LTS o GR/GRS/G.
   - ML entero → ml tal cual (`3030 ML` → 3030).
   - ML con decimales y valor < 100 → se interpreta como litros (`1.5ML` → 1500) y se avisa.
   - L/LT/LTS → litros × 1000 (con aviso).
   - GR/GRS/G (peso) → `medida_ml = None` y aviso (`70 GRS`).
3. Unidades por paquete: el entero que sigue a la medida (`6`, `6 pack`, `12 MC`); sin él, 1.
4. Marca = primera palabra; sabor = palabras siguientes hasta el primer marcador de envase
   (PET, VIDRIO, TETRA, SOBRETAPA, DISPLAY, REGULAR, NO, RETORNABLE, LATA) o la medida.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

MAX_SABOR = 60

_MARCADORES = frozenset(
    {"PET", "VIDRIO", "TETRA", "SOBRETAPA", "DISPLAY", "REGULAR", "NO", "RETORNABLE", "LATA"}
)
_RE_MEDIDA = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)\s*(ML|GRS|GR|LTS|LT|L|G)\b", re.IGNORECASE)
_RE_UNIDADES = re.compile(r"\s*(\d+)\b")
_RE_UNIDADES_FINAL = re.compile(r"(\d+)\s*(?:PACK|MC|UN)?\s*$", re.IGNORECASE)
_RE_PINA = re.compile("PI�A", re.IGNORECASE)
_ILEGIBLE = "�"
_UNIDAD_PESO = frozenset({"GR", "GRS", "G"})
_UNIDAD_LITRO = frozenset({"L", "LT", "LTS"})


@dataclass
class DescripcionProducto:
    nombre: str
    marca: str | None
    sabor: str | None
    medida_ml: int | None
    unidades_por_paquete: int
    avisos: list[str] = field(default_factory=list)


def normalizar_texto_catalogo(texto: str) -> tuple[str, list[str]]:
    """Espacios, NFC y mojibake conocido. Devuelve el texto y los avisos de lo corregido."""
    avisos: list[str] = []
    limpio = unicodedata.normalize("NFC", texto)
    if _RE_PINA.search(limpio):
        limpio = _RE_PINA.sub("PIÑA", limpio)
        avisos.append("caracter_corregido: PI�A -> PIÑA")
    if _ILEGIBLE in limpio:
        avisos.append("caracter_ilegible: la descripción conserva un carácter no interpretable")
    return re.sub(r"\s+", " ", limpio).strip(), avisos


def _decimal(texto: str) -> Decimal | None:
    try:
        return Decimal(texto.replace(",", "."))
    except InvalidOperation:
        return None


def _medida_ml(numero: str, unidad: str, avisos: list[str]) -> int | None:
    unidad = unidad.upper()
    valor = _decimal(numero)
    if valor is None:
        avisos.append(f"medida_no_interpretable: «{numero} {unidad}»")
        return None
    if unidad in _UNIDAD_PESO:
        avisos.append(f"sin_medida_ml: unidad de peso «{numero} {unidad}»")
        return None
    if unidad in _UNIDAD_LITRO:
        avisos.append(f"medida_en_litros: «{numero} {unidad}» -> {int(valor * 1000)} ml")
        return int(valor * 1000)
    if valor != valor.to_integral_value():
        if valor < 100:
            avisos.append(f"medida_en_litros: «{numero} {unidad}» -> {int(valor * 1000)} ml")
            return int(valor * 1000)
        avisos.append(f"medida_redondeada: «{numero} {unidad}» -> {int(round(valor))} ml")
        return int(round(valor))
    return int(valor)


def _sabor(prefijo: str, avisos: list[str]) -> tuple[str | None, str | None]:
    palabras = prefijo.split()
    if not palabras:
        return None, None
    marca, resto = palabras[0], palabras[1:]
    sabor: list[str] = []
    for palabra in resto:
        if palabra.upper().strip(",") in _MARCADORES:
            break
        sabor.append(palabra)
    texto = " ".join(sabor).strip(" ,-")
    if not texto:
        avisos.append("sin_sabor: la descripción no indica sabor")
        return marca, None
    if len(texto) > MAX_SABOR:
        avisos.append(f"sabor_truncado: «{texto}» -> {MAX_SABOR} caracteres")
        texto = texto[:MAX_SABOR].rstrip()
    return marca, texto


def interpretar_descripcion(descripcion: str) -> DescripcionProducto:
    nombre, avisos = normalizar_texto_catalogo(descripcion)
    medida_ml: int | None = None
    unidades: int | None = None
    prefijo = nombre

    coincidencia = _RE_MEDIDA.search(nombre)
    if coincidencia:
        prefijo = nombre[: coincidencia.start()]
        medida_ml = _medida_ml(coincidencia.group(1), coincidencia.group(2), avisos)
        resto = _RE_UNIDADES.match(nombre, coincidencia.end())
        if resto:
            unidades = int(resto.group(1))
    else:
        avisos.append("sin_medida: la descripción no trae medida con unidad")
        final = _RE_UNIDADES_FINAL.search(nombre)
        if final:
            unidades = int(final.group(1))
            prefijo = nombre[: final.start()]

    if unidades is None or unidades <= 0:
        avisos.append("sin_unidades_por_paquete: se asume 1")
        unidades = 1

    marca, sabor = _sabor(prefijo, avisos)
    return DescripcionProducto(
        nombre=nombre,
        marca=marca,
        sabor=sabor,
        medida_ml=medida_ml,
        unidades_por_paquete=unidades,
        avisos=avisos,
    )
