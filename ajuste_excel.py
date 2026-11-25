# ============================================================================
# AJUSTE AUTOMÁTICO DE CELDAS EN LOS EXCEL
# ============================================================================
# Activa "Ajustar texto", ensancha columnas donde una cantidad no cabe y
# aumenta el alto de las filas según el contenido. Nunca reduce un tamaño.

import math
import textwrap
from copy import copy

from openpyxl.utils import get_column_letter

ANCHO_DEFAULT = 8.43
ALTO_DEFAULT = 15.0


def _ancho(ws, col):
    letra = get_column_letter(col)
    if letra in ws.column_dimensions:
        return ws.column_dimensions[letra].width or ANCHO_DEFAULT
    # openpyxl agrupa columnas contiguas del mismo ancho
    for dim in ws.column_dimensions.values():
        if dim.min and dim.max and dim.min <= col <= dim.max:
            return dim.width or ANCHO_DEFAULT
    return ANCHO_DEFAULT


def _largo_numero(celda):
    valor, formato = celda.value, celda.number_format or ''
    if '%' in formato:
        return len(f"{valor * 100:,.2f}%")
    decimales = 2 if '.00' in formato else 0
    extra = 2 if '$' in formato else 0
    return len(f"{valor:,.{decimales}f}") + extra


def _lineas(texto, caracteres):
    total = 0
    for parrafo in str(texto).split('\n'):
        total += max(1, len(textwrap.wrap(parrafo, width=max(1, caracteres))))
    return total


def autoajustar_hoja(ws):
    combinadas = {}
    ocultas = set()
    for rango in ws.merged_cells.ranges:
        combinadas[(rango.min_row, rango.min_col)] = rango
        for f in range(rango.min_row, rango.max_row + 1):
            for c in range(rango.min_col, rango.max_col + 1):
                if (f, c) != (rango.min_row, rango.min_col):
                    ocultas.add((f, c))

    # 1) Columnas: que las cantidades no se muestren como ####
    necesarios = {}
    for fila in ws.iter_rows():
        for celda in fila:
            posicion = (celda.row, celda.column)
            if posicion in ocultas or posicion in combinadas:
                continue
            if isinstance(celda.value, (int, float)) and not isinstance(celda.value, bool):
                tam = (celda.font.sz or 11) / 11
                if celda.font.b:
                    tam *= 1.08
                ancho = _largo_numero(celda) * tam + 2
                necesarios[celda.column] = max(ancho, necesarios.get(celda.column, 0))
    for col, ancho in necesarios.items():
        if ancho > _ancho(ws, col):
            ws.column_dimensions[get_column_letter(col)].width = round(ancho, 1)

    # 2) Texto: ajustar y calcular el alto de cada fila
    altos = {}
    for fila in ws.iter_rows():
        for celda in fila:
            posicion = (celda.row, celda.column)
            texto = celda.value
            if posicion in ocultas or texto is None or isinstance(texto, (int, float)):
                continue
            texto = str(texto)
            if texto.startswith('='):
                continue

            rango = combinadas.get(posicion)
            if rango is None:
                derecha_libre = ws.cell(celda.row, celda.column + 1).value is None
                # Texto sin ajuste que se extiende sobre celdas vacías: se deja igual
                if derecha_libre and not celda.alignment.wrap_text and '\n' not in texto:
                    continue
                columnas = [celda.column]
                filas = [celda.row]
            else:
                columnas = range(rango.min_col, rango.max_col + 1)
                filas = list(range(rango.min_row, rango.max_row + 1))

            alineacion = copy(celda.alignment)
            alineacion.wrap_text = True
            celda.alignment = alineacion

            puntos = celda.font.sz or 11
            factor = puntos / 11 * (1.1 if celda.font.b else 1.0)
            ancho = sum(_ancho(ws, c) for c in columnas)
            caracteres = int((ancho - 1) * 1.05 / factor)
            alto = math.ceil(_lineas(texto, caracteres) * puntos * 1.35 + 3)

            actual = sum(ws.row_dimensions[f].height or ALTO_DEFAULT for f in filas)
            if alto > actual:
                ultima = filas[-1]
                base = ws.row_dimensions[ultima].height or ALTO_DEFAULT
                altos[ultima] = max(base + alto - actual, altos.get(ultima, 0))
    for f, alto in altos.items():
        ws.row_dimensions[f].height = alto


def autoajustar_libro(wb):
    for ws in wb.worksheets:
        autoajustar_hoja(ws)
