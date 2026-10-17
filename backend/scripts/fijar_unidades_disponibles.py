# -*- coding: utf-8 -*-
"""Pone las noches disponibles de un escenario en `unidades × días del mes`.

Owner, 2026-10-16: *«hay que corregir forecast 2026, hay que poner 11 unidades
en la cuenta 9010»*.

La cuenta estadística **9010** es la que trae las noches disponibles cuando se
sube un actual (`gl_detail_importer`). En la base aterriza en
`scenario_stats.rooms_available`, que es lo que esto escribe.

## ⚠️ Toca UN escenario, nombrado en la línea de comandos

Las noches disponibles son el denominador de la ocupación, del RevPAR, del
TRevPAR y del punto de equilibrio. Cambiarlas en el escenario equivocado no
falla: deja esos indicadores corridos en una versión que nadie está mirando, y
el total sigue cuadrando consigo mismo.

## ⚠️ No toca las noches OCUPADAS ni los pax

Esos son lo que se vendió. Acá se corrige cuántas unidades estuvieron a la
venta, que es otra cosa. La ocupación se recalcula sobre el denominador nuevo.

Uso:
    python -m scripts.fijar_unidades_disponibles "FORECAST Working 2026" 11
    python -m scripts.fijar_unidades_disponibles "FORECAST Working 2026" 11 --aplicar
"""
from __future__ import annotations

import asyncio
import sys
from decimal import Decimal

from sqlalchemy import select

from app.db import SessionLocal
from app.hotel_actual import HOTEL_ID
from app.models.scenario import Scenario
from app.models.scenario_stat import ScenarioStat

MES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
       "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
#: El mismo calendario del motor (`revenue_calculator.CALENDAR_DAYS`), a
#: propósito: si acá se contaran los días distinto, el escenario tendría dos
#: denominadores para el mismo mes.
DIAS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
D = lambda v: Decimal(str(v or 0))


async def main(nombre: str, unidades: int, aplicar: bool) -> int:
    async with SessionLocal() as db:
        escs = (await db.execute(select(Scenario).where(
            Scenario.hotel_id == HOTEL_ID))).scalars().all()
        cand = [s for s in escs
                if f"{s.type} {s.version} {s.year}".strip() == nombre]
        if len(cand) != 1:
            print(f"✗ Se buscaba exactamente un escenario «{nombre}» y hay "
                  f"{len(cand)}. Los que hay:")
            for s in sorted(escs, key=lambda x: (x.year, x.type)):
                print(f"    {s.type} {s.version} {s.year}")
            return 2
        esc = cand[0]
        print(f"escenario: {esc.type} {esc.version} {esc.year}   id={esc.id}")
        if esc.is_locked:
            print("✗ Está enllavado. No se toca.")
            return 2

        sts = {int(s.month): s for s in (await db.execute(select(ScenarioStat).where(
            ScenarioStat.scenario_id == esc.id))).scalars()}
        print(f"\n  mes   antes   ahora   ocupadas   ocup. antes → ahora")
        antes_tot = despues_tot = 0
        cambios = 0
        for m in range(1, 13):
            nuevo = unidades * DIAS[m - 1]
            st = sts.get(m)
            if st is None:
                print(f"  {MES[m-1]}      —   {nuevo:>5}          —   "
                      f"(el mes no existe en este escenario, se salta)")
                continue
            viejo = int(st.rooms_available or 0)
            occ = D(st.rooms_occupied)
            antes_tot += viejo
            despues_tot += nuevo
            o1 = (float(occ) / viejo * 100) if viejo else 0
            o2 = (float(occ) / nuevo * 100) if nuevo else 0
            marca = " " if viejo == nuevo else "←"
            print(f"  {MES[m-1]}  {viejo:>5}   {nuevo:>5}   {float(occ):>8.0f}   "
                  f"{o1:>5.1f}% → {o2:>5.1f}%  {marca}")
            if viejo != nuevo:
                cambios += 1
                if aplicar:
                    st.rooms_available = nuevo
                    st.occupancy_pct = (occ / Decimal(nuevo)) if nuevo else Decimal("0")

        print(f"\n  año: {antes_tot:,} → {despues_tot:,} noches disponibles")
        if not aplicar:
            await db.rollback()
            print(f"\nENSAYO: {cambios} mes(es) cambiarían. Nada se guardó.")
            return 0
        await db.commit()
        print(f"\n✓ Guardado: {cambios} mes(es) corregidos.")
        return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--aplicar"]
    if len(args) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(
        main(args[0], int(args[1]), "--aplicar" in sys.argv)))
