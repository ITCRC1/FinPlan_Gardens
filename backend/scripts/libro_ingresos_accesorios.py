# -*- coding: utf-8 -*-
"""Arma el libro de ingresos accesorios, en el formato del de Oxygen.

Owner, 2026-11-02: *«podés hacer este mismo formato para Ojochal Garden»*.

Lee el JSON que imprime `scripts.datos_ingresos_accesorios` y escribe el .xlsx.
Va afuera del contenedor a propósito: ahí no hay de dónde bajar el archivo.

## Lo que copia del libro de Oxygen, y lo que no

Copia la FORMA: una pestaña por línea, los doce meses con noches, pax,
ocupación, ADR e ingreso de cada período, el $/pax y el $/noche al lado, una
columna amarilla para teclear, y dos columnas de referencia que dicen cuánto
daría el mes aplicando el $/pax de un año anterior a los pax presupuestados.

No copia las LÍNEAS. Ojochal factura su restaurante en `REV_SABOR_OJOCHAL` y
no tiene Beverage ni Laundry a huéspedes: un libro con las pestañas de Oxygen
serían nueve tabs vacíos y dos que importan. Las pestañas salen de lo que esta
propiedad tiene cargado.

Uso:
    python -m scripts.libro_ingresos_accesorios datos.json salida.xlsx
"""
from __future__ import annotations

import json
import pathlib
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L

MES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
       "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

#: Lo que NO es accesorio.
ROOMS = {"REV_ROOMS", "REV_ROOMS_OTHER"}

AZUL = PatternFill("solid", fgColor="DDEBF7")      # se teclea
AMAR = PatternFill("solid", fgColor="FFF2CC")      # la columna a llenar
GRIS = PatternFill("solid", fgColor="F2F2F2")
CAB = PatternFill("solid", fgColor="1F4E4A")
TOT = PatternFill("solid", fgColor="E2EFDA")
B_FINA = Border(bottom=Side("thin", color="BFBFBF"))

USD = '#,##0.00'
PCT = '0.0%'
NUM = '#,##0'


#: Excel no admite estos caracteres en el nombre de una pestaña, y el nombre
#: de la línea viene del reporte —«Other / Misc Revenue»—, así que hay que
#: limpiarlo. Se reemplaza por un guion y no se borra: «Other  Misc» se lee
#: peor que «Other - Misc».
PROHIBIDOS = r'/\?*[]:'


def _nombre_de_hoja(texto: str) -> str:
    for ch in PROHIBIDOS:
        texto = texto.replace(ch, "-")
    return " ".join(texto.split())[:28].strip()


def _cab(ws, fila, col, texto, ancho=None):
    c = ws.cell(fila, col, texto)
    c.font = Font(bold=True, color="FFFFFF", size=9)
    c.fill = CAB
    c.alignment = Alignment(horizontal="center", wrap_text=True, vertical="center")
    if ancho:
        ws.column_dimensions[L(col)].width = ancho
    return c


def _leeme(wb, d, lineas, hasta_2026):
    ws = wb.create_sheet("Léame")
    ws.column_dimensions["B"].width = 118
    ws["B2"] = f"{d['hotel_name'].upper()} · Ingresos accesorios al Rooms Only"
    ws["B2"].font = Font(bold=True, size=14, color="1F4E4A")

    def p(fila, texto, bold=False, color="000000"):
        ws.cell(fila, 2, texto).font = Font(bold=bold, size=10, color=color)
        ws.cell(fila, 2).alignment = Alignment(wrap_text=True, vertical="top")

    p(5, "Para qué es este libro", True)
    p(6, "Una pestaña por línea de ingreso accesorio. Cada una trae los doce "
         "meses con las noches, los pax, la ocupación, el ADR y el ingreso "
         "—reales 2025, reales 2026 y el Budget 2027 que hoy tiene el "
         "sistema— más el ingreso por pax y por noche de cada uno.")
    p(7, "La columna amarilla «TU ESTIMADO 2027» es para teclear. Al escribir "
         "un monto, el $/pax y el $/noche de al lado se recalculan solos, y el "
         "Resumen se actualiza.")
    p(9, "Qué mirar en cada mes", True)
    p(10, "Las dos últimas columnas dicen cuánto daría ese mes si se le "
          "aplicara el $/pax de 2025 o el de 2026 a los pax presupuestados de "
          "2027. No son una recomendación: son el punto de partida para "
          "discutir si ese mes se parece al del año pasado o no.")

    fila = 12
    if hasta_2026 < 12:
        p(fila, f"⚠️  2026 llega sólo hasta {MES[hasta_2026 - 1].lower()}", True,
          "C00000")
        p(fila + 1, "Son los meses cerrados en el sistema. El resto aparece "
                    "vacío, no en cero. Un promedio anual de 2026 calculado "
                    f"sobre doce meses estaría dividiendo entre doce lo que "
                    f"pasó en {hasta_2026}.")
        fila += 3

    p(fila, "⚠️  Las pestañas son las líneas de ESTA propiedad", True, "C00000")
    p(fila + 1, "No las de Oxygen. Ojochal factura su restaurante en «Sabor "
                "Ojochal» y no tiene Beverage ni Laundry a huéspedes. Las "
                "líneas del reporte que hoy están en cero en los tres períodos "
                "no traen pestaña: están listadas en el Resumen para que se "
                "vean, y si hay que presupuestar alguna se agrega.")
    fila += 3

    p(fila, "⚠️  El Rooms de 2027 sale del modelo por segmento de venta", True,
      "C00000")
    p(fila + 1, "El tarifario RAC, con el descuento cargado a mano por mes. Por "
                "eso el ADR de 2027 no se compara contra el de 2025 como si "
                "fueran el mismo cálculo: lo comparable son los pax y las "
                "noches, que es con lo que se mueven estas líneas.")
    fila += 3

    p(fila, "Colores", True)
    p(fila + 1, "Azul = viene del sistema.    Negro = fórmula, no tocar.    "
                "Amarillo = la columna a llenar.")
    p(fila + 3, f"Datos extraídos de FinPlan {d['hotel_id']} el 2 de noviembre "
                f"de 2026, por el mismo motor que alimenta el P&L y Hotel "
                f"Consolidation.", color="808080")


def _drivers(wb, escs):
    ws = wb.create_sheet("Drivers")
    ws["A1"] = "DRIVERS DEL HOTEL · lo que mueve cada línea accesoria"
    ws["A1"].font = Font(bold=True, size=12, color="1F4E4A")
    ws["A2"] = ("Las mismas noches y pax que usan todas las pestañas. Acá están "
                "juntos para ver la estacionalidad de un vistazo.")
    ws["A2"].font = Font(size=9, color="808080")
    ws.column_dimensions["A"].width = 13

    campos = ["Disponibles", "Noches ocup.", "de las cuales cortesía",
              "Noches que cobran", "Pax", "% Ocupación", "Room Revenue", "ADR"]
    for i, e in enumerate(escs):
        c0 = 2 + i * 8
        ws.cell(3, c0, e["titulo"]).font = Font(bold=True, size=10,
                                                color="1F4E4A")
        for j, nom in enumerate(campos):
            _cab(ws, 4, c0 + j, nom, 11)

    for m in range(12):
        f = 5 + m
        ws.cell(f, 1, MES[m]).font = Font(size=9)
        for i, e in enumerate(escs):
            c0 = 2 + i * 8
            d = e["meses"][m]
            cob = L(c0 + 3)
            if d["disponibles"] or d["ocupadas"]:
                ws.cell(f, c0, d["disponibles"]).number_format = NUM
                ws.cell(f, c0 + 1, d["ocupadas"]).number_format = NUM
                if e["rooms_source"] == "canales":
                    ws.cell(f, c0 + 2, d["cortesia"]).number_format = NUM
                ws.cell(f, c0 + 4, d["pax"]).number_format = NUM
                ws.cell(f, c0 + 6, e["rooms"][m]).number_format = USD
            # Las que cobran salen de restar la cortesía: una resta a la vista
            # vale más que un número que hay que creer.
            ws.cell(f, c0 + 3, f"={L(c0+1)}{f}-N({L(c0+2)}{f})").number_format = NUM
            ws.cell(f, c0 + 5,
                    f'=IFERROR({L(c0+1)}{f}/{L(c0)}{f},"")').number_format = PCT
            ws.cell(f, c0 + 7,
                    f'=IFERROR({L(c0+6)}{f}/{cob}{f},"")').number_format = USD

    f = 17
    ws.cell(f, 1, "TOTAL").font = Font(bold=True)
    for i, e in enumerate(escs):
        c0 = 2 + i * 8
        for j in (0, 1, 2, 3, 4, 6):
            ws.cell(f, c0 + j,
                    f"=SUM({L(c0+j)}5:{L(c0+j)}16)").number_format = (
                        USD if j == 6 else NUM)
        ws.cell(f, c0 + 5,
                f'=IFERROR({L(c0+1)}{f}/{L(c0)}{f},"")').number_format = PCT
        ws.cell(f, c0 + 7,
                f'=IFERROR({L(c0+6)}{f}/{L(c0+3)}{f},"")').number_format = USD
        for j in range(8):
            ws.cell(f, c0 + j).fill = TOT
            ws.cell(f, c0 + j).font = Font(bold=True, size=9)
    ws.cell(f, 1).fill = TOT
    ws.freeze_panes = "B5"


def _hoja_linea(wb, nombre, code, escs, hoja):
    ws = wb.create_sheet(hoja)
    ws["A1"] = f"{nombre.upper()}  ·  {code}"
    ws["A1"].font = Font(bold=True, size=12, color="1F4E4A")
    ws["A2"] = ("Teclee el monto del mes en la columna amarilla. El $/pax y el "
                "$/noche de al lado se recalculan solos.")
    ws["A2"].font = Font(size=9, color="808080")
    ws.column_dimensions["A"].width = 13

    campos = ["Noches", "Pax", "% Ocup.", "ADR hab.", "Ingreso", "$ / Pax",
              "$ / Noche"]
    for i, e in enumerate(escs):
        c0 = 2 + i * 7
        ws.cell(4, c0, e["titulo"]).font = Font(bold=True, size=10,
                                                color="1F4E4A")
        for j, nom in enumerate(campos):
            _cab(ws, 5, c0 + j, nom, 11)

    ce = 2 + len(escs) * 7                    # primera columna del estimado
    ws.cell(4, ce, "TU ESTIMADO 2027").font = Font(bold=True, size=10,
                                                   color="BF8F00")
    for j, nom in enumerate(["Monto", "$ / Pax", "$ / Noche", "Δ vs sistema"]):
        c = _cab(ws, 5, ce + j, nom, 12)
        if j == 0:
            c.fill = PatternFill("solid", fgColor="BF8F00")
    cr = ce + 4
    ws.cell(4, cr, "Referencia: si aplico el $/pax de…").font = Font(
        bold=True, size=10, color="808080")
    for j, e in enumerate(escs[:-1]):
        _cab(ws, 5, cr + j, f"…{e['year']} a los pax de {escs[-1]['year']}", 15)

    ult = 2 + (len(escs) - 1) * 7             # el bloque del presupuesto
    for m in range(12):
        f = 6 + m
        ws.cell(f, 1, MES[m]).font = Font(size=9)
        for i, e in enumerate(escs):
            c0 = 2 + i * 7
            d = e["meses"][m]
            monto = e["lineas"].get(code, {}).get("meses", [0] * 12)[m]
            hay = bool(d["disponibles"] or d["ocupadas"])
            if hay:
                ws.cell(f, c0, d["ocupadas"]).number_format = NUM
                ws.cell(f, c0 + 1, d["pax"]).number_format = NUM
                ws.cell(f, c0 + 4, monto).number_format = USD
                for j in (0, 1, 4):
                    ws.cell(f, c0 + j).fill = AZUL
            # Ocupación y ADR se traen de Drivers: un solo lugar donde miran.
            dj = 5 + m
            ws.cell(f, c0 + 2, f"=Drivers!{L(2 + i * 8 + 5)}{dj}"
                    ).number_format = PCT
            ws.cell(f, c0 + 3, f"=Drivers!{L(2 + i * 8 + 7)}{dj}"
                    ).number_format = USD
            ws.cell(f, c0 + 5,
                    f'=IFERROR({L(c0+4)}{f}/{L(c0+1)}{f},"")').number_format = USD
            ws.cell(f, c0 + 6,
                    f'=IFERROR({L(c0+4)}{f}/{L(c0)}{f},"")').number_format = USD

        # El estimado arranca igual al sistema: así, bajar y subir sin tocar
        # nada no cambia el presupuesto.
        ws.cell(f, ce, f"={L(ult+4)}{f}").number_format = USD
        ws.cell(f, ce).fill = AMAR
        ws.cell(f, ce + 1,
                f'=IFERROR({L(ce)}{f}/{L(ult+1)}{f},"")').number_format = USD
        ws.cell(f, ce + 2,
                f'=IFERROR({L(ce)}{f}/{L(ult)}{f},"")').number_format = USD
        ws.cell(f, ce + 3, f"={L(ce)}{f}-{L(ult+4)}{f}").number_format = USD
        for j, e in enumerate(escs[:-1]):
            c0 = 2 + j * 7
            ws.cell(f, cr + j,
                    f'=IFERROR({L(c0+4)}{f}/{L(c0+1)}{f}*{L(ult+1)}{f},"")'
                    ).number_format = USD

    f = 18
    ws.cell(f, 1, "TOTAL").font = Font(bold=True)
    ws.cell(f, 1).fill = TOT
    for i, e in enumerate(escs):
        c0 = 2 + i * 7
        for j in (0, 1, 4):
            ws.cell(f, c0 + j, f"=SUM({L(c0+j)}6:{L(c0+j)}17)"
                    ).number_format = USD if j == 4 else NUM
        ws.cell(f, c0 + 5,
                f'=IFERROR({L(c0+4)}{f}/{L(c0+1)}{f},"")').number_format = USD
        ws.cell(f, c0 + 6,
                f'=IFERROR({L(c0+4)}{f}/{L(c0)}{f},"")').number_format = USD
        for j in range(7):
            ws.cell(f, c0 + j).fill = TOT
            ws.cell(f, c0 + j).font = Font(bold=True, size=9)
    ws.cell(f, ce, f"=SUM({L(ce)}6:{L(ce)}17)").number_format = USD
    ws.cell(f, ce + 1,
            f'=IFERROR({L(ce)}{f}/{L(ult+1)}{f},"")').number_format = USD
    ws.cell(f, ce + 2,
            f'=IFERROR({L(ce)}{f}/{L(ult)}{f},"")').number_format = USD
    ws.cell(f, ce + 3, f"={L(ce)}{f}-{L(ult+4)}{f}").number_format = USD
    for j in range(4):
        ws.cell(f, ce + j).fill = TOT
        ws.cell(f, ce + j).font = Font(bold=True, size=9)
    ws.freeze_panes = "B6"


def _resumen(wb, escs, lineas, hojas):
    ws = wb.create_sheet("Resumen", 1)
    ws["A1"] = "RESUMEN · ingresos accesorios al Rooms Only"
    ws["A1"].font = Font(bold=True, size=12, color="1F4E4A")
    ws["A2"] = ("Se llena solo desde las pestañas de cada línea. No hay nada "
                "que teclear acá.")
    ws["A2"].font = Font(size=9, color="808080")
    ws.column_dimensions["A"].width = 30

    cols = ["Línea"] + [e["titulo"] for e in escs] + [
        "TU ESTIMADO 2027", "Δ vs sistema"] + [
        f"$/Pax {e['year']}" for e in escs]
    for j, nom in enumerate(cols, start=1):
        _cab(ws, 4, j, nom, 17 if j > 1 else 30)

    f = 5
    for code, nom, hoja in lineas:
        ws.cell(f, 1, nom).font = Font(size=9)
        if hoja:
            h = f"'{hoja}'" if " " in hoja or "&" in hoja else hoja
            for i, e in enumerate(escs):
                ws.cell(f, 2 + i, f"={h}!{L(2 + i * 7 + 4)}18").number_format = USD
            ce = 2 + len(escs) * 7
            ws.cell(f, 2 + len(escs), f"={h}!{L(ce)}18").number_format = USD
            ws.cell(f, 3 + len(escs),
                    f"={L(2 + len(escs))}{f}-{L(1 + len(escs))}{f}"
                    ).number_format = USD
            for i, e in enumerate(escs):
                ws.cell(f, 4 + len(escs) + i,
                        f"={h}!{L(2 + i * 7 + 5)}18").number_format = USD
        else:
            # Sin pestaña: la línea existe en el reporte y hoy está en cero en
            # los tres períodos. Se lista igual — una línea invisible es una
            # línea que nadie presupuesta.
            for i in range(len(escs) + 2):
                ws.cell(f, 2 + i, 0).number_format = USD
            ws.cell(f, 1).font = Font(size=9, color="808080", italic=True)
        f += 1

    ws.cell(f, 1, "TOTAL ACCESORIOS").font = Font(bold=True)
    for j in range(2, 4 + len(escs)):
        ws.cell(f, j, f"=SUM({L(j)}5:{L(j)}{f-1})").number_format = USD
    for j in range(1, len(cols) + 1):
        ws.cell(f, j).fill = TOT
        ws.cell(f, j).font = Font(bold=True, size=9)

    fr = f + 2
    ws.cell(fr, 1, "Room Revenue (contexto)").font = Font(size=9, color="808080")
    for i, e in enumerate(escs):
        ws.cell(fr, 2 + i, sum(e["rooms"])).number_format = USD
    ws.cell(fr + 1, 1, "Accesorios / Rooms").font = Font(size=9, color="808080")
    for i in range(len(escs)):
        ws.cell(fr + 1, 2 + i,
                f'=IFERROR({L(2+i)}{f}/{L(2+i)}{fr},"")').number_format = PCT
    ws.cell(fr + 1, 2 + len(escs),
            f'=IFERROR({L(2+len(escs))}{f}/{L(1+len(escs))}{fr},"")'
            ).number_format = PCT


def main(entrada: str, salida: str) -> int:
    d = json.loads(pathlib.Path(entrada).read_text(encoding="utf-8"))

    escs = []
    for e in d["escenarios"]:
        cerrados = sum(1 for m in e["meses"] if m["disponibles"] or m["ocupadas"])
        titulo = (f"Real {e['year']}" if e["type"] == "ACTUAL"
                  else f"Budget {e['year']} · sistema")
        if e["type"] == "ACTUAL" and cerrados < 12:
            titulo += f" (ene–{MES[cerrados-1].lower()[:3]})"
        e["titulo"] = titulo
        e["rooms"] = e["lineas"].get("REV_ROOMS", {}).get("meses", [0] * 12)
        e["cerrados"] = cerrados
        escs.append(e)

    # Qué líneas llevan pestaña: las que tienen monto en ALGÚN período.
    codes = sorted({c for e in escs for c in e["lineas"] if c.startswith("REV")}
                   - ROOMS)
    con_dato = [c for c in codes
                if any(sum(e["lineas"].get(c, {}).get("meses", [])) for e in escs)]
    nombre_de = {c: next((e["lineas"][c]["nombre"] for e in escs
                          if c in e["lineas"] and e["lineas"][c]["nombre"]), c)
                 for c in codes}
    usados: set[str] = set()
    lineas = []
    for c in codes:
        if c in con_dato:
            hoja = _nombre_de_hoja(nombre_de[c]) or c
            while hoja in usados:
                hoja += "_"
            usados.add(hoja)
            lineas.append((c, nombre_de[c], hoja))
        else:
            lineas.append((c, nombre_de[c] + "  (sin movimiento)", None))

    wb = Workbook()
    wb.remove(wb.active)
    hasta = next((e["cerrados"] for e in escs
                  if e["type"] == "ACTUAL" and e["cerrados"] < 12), 12)
    _leeme(wb, d, lineas, hasta)
    _drivers(wb, escs)
    for code, nom, hoja in lineas:
        if hoja:
            _hoja_linea(wb, nom, code, escs, hoja)
    _resumen(wb, escs, lineas, [h for _, _, h in lineas if h])
    wb.save(salida)
    print(f"✓ {salida}")
    print(f"  pestañas con dato: {[h for _, _, h in lineas if h]}")
    print(f"  listadas sin pestaña: "
          f"{[c for c, _, h in lineas if not h]}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
