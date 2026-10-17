# -*- coding: utf-8 -*-
"""Lleva los meses CERRADOS del ACTUAL 2026 al FORECAST 2026 Working.

Owner, 2026-10-16, mostrando los doce meses del forecast con enero-julio en la
disponibilidad real: *«hay que revisar todo y que quede bien»*.

## Qué estaba pasando

Un forecast es **meses cerrados reales + meses futuros proyectados**. El de
2026 sólo tenía agosto-diciembre: enero a julio no existían, así que el año
leía **1.683 noches disponibles** en vez de 4.162 — y todo lo que se divide por
noches (ocupación, RevPAR, TRevPAR, punto de equilibrio) salía sobre el
denominador de cinco meses.

No fallaba nada. El cuadro de Disponibilidad mostraba cinco columnas con
número y siete vacías, y el total de abajo sumaba sólo lo que había.

## Qué copia, y qué NO

Copia de `scenario_stats` del ACTUAL: **noches disponibles, ocupadas y pax**.
Son la medición de lo que pasó.

⚠️ **No toca el ingreso.** Ni el del forecast ni el del actual: eso es un
cierre de mes, no una estadística, y moverlo desde acá sería escribir plata en
un escenario sin que nadie lo haya decidido.

⚠️ **No pisa un mes que el forecast ya tenga.** Si alguien proyectó un mes a
mano, se respeta y se dice cuál.

Uso:
    python -m scripts.forecast_2026_meses_cerrados            # ensayo
    python -m scripts.forecast_2026_meses_cerrados --aplicar
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from decimal import Decimal

from sqlalchemy import select

from app.db import SessionLocal
from app.hotel_actual import HOTEL_ID
from app.models.scenario import Scenario
from app.models.scenario_stat import ScenarioStat

ANIO = 2026
MES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
       "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
D = lambda v: Decimal(str(v or 0))


async def _uno(db, tipo: str) -> Scenario:
    filas = (await db.execute(select(Scenario).where(
        Scenario.hotel_id == HOTEL_ID, Scenario.year == ANIO,
        Scenario.type == tipo))).scalars().all()
    if len(filas) != 1:
        raise SystemExit(f"Se esperaba un solo {tipo} de {ANIO} y hay {len(filas)}")
    return filas[0]


async def main(aplicar: bool) -> int:
    async with SessionLocal() as db:
        act = await _uno(db, "ACTUAL")
        fc = await _uno(db, "FORECAST")
        print(f"origen : {act.type} {act.version} {act.year}")
        print(f"destino: {fc.type} {fc.version} {fc.year}")
        if fc.is_locked:
            print("✗ El forecast está enllavado. No se toca.")
            return 2

        de_act = {int(s.month): s for s in (await db.execute(select(ScenarioStat).where(
            ScenarioStat.scenario_id == act.id))).scalars()}
        de_fc = {int(s.month): s for s in (await db.execute(select(ScenarioStat).where(
            ScenarioStat.scenario_id == fc.id))).scalars()}

        print(f"\n  mes   actual(disp/occ)      forecast        acción")
        copiados = 0
        for m in range(1, 13):
            a = de_act.get(m)
            f = de_fc.get(m)
            izq = (f"{int(a.rooms_available or 0):>4}/{float(D(a.rooms_occupied)):>6.0f}"
                   if a else "   —/     —")
            der = (f"{int(f.rooms_available or 0):>4}/{float(D(f.rooms_occupied)):>6.0f}"
                   if f else "   —/     —")
            if f is not None:
                print(f"  {MES[m-1]}   {izq}        {der}        ya tiene, se respeta")
                continue
            if a is None:
                print(f"  {MES[m-1]}   {izq}        {der}        sin medir, se salta")
                continue
            print(f"  {MES[m-1]}   {izq}        {der}        ← se copia")
            copiados += 1
            if aplicar:
                db.add(ScenarioStat(
                    id=str(uuid.uuid4()), scenario_id=fc.id, month=m,
                    rooms_available=int(a.rooms_available or 0),
                    rooms_occupied=D(a.rooms_occupied),
                    guests=D(a.guests),
                    occupancy_pct=D(a.occupancy_pct),
                    # ⚠️ El ADR viaja con las noches porque sale de ellas y del
                    # ingreso del mes cerrado. Si el actual no lo tiene, queda
                    # en cero — inventarlo sería peor.
                    adr=D(a.adr)))

        disp = sum(int(s.rooms_available or 0) for s in de_fc.values())
        nuevo = disp + sum(int(de_act[m].rooms_available or 0)
                           for m in range(1, 13)
                           if m not in de_fc and m in de_act)
        print(f"\n  noches disponibles del año: {disp:,} → {nuevo:,}")

        if not aplicar:
            await db.rollback()
            print(f"\nENSAYO: {copiados} mes(es) se copiarían. Nada se guardó.")
            return 0
        await db.commit()
        print(f"\n✓ Guardado: {copiados} mes(es) copiados.")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main("--aplicar" in sys.argv)))
