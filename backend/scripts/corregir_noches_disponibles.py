# -*- coding: utf-8 -*-
"""Pone las noches disponibles de los escenarios `checkbook` en unidades × días.

## Por qué hace falta un script y no alcanza con el arreglo del motor

El motor ya las calcula bien (`revenue_results_from_checkbook`), pero
`scenario_stats` guarda el número viejo y hay reportes que lo leen de ahí
directamente. El valor guardado sólo se reescribe en un recálculo completo —y
**recalcular un ACTUAL no es inocente**: recompone planilla, allocations y P&L
de meses que ya están cerrados.

Esto toca una sola cosa: `rooms_available`, y `occupancy_pct` que se deriva de
ella. Las noches OCUPADAS, los pax y el ADR no se tocan: son dato real y no
salen del inventario.

## ⚠️ No toca los escenarios en modo `drivers`

Ésos ya calculan las disponibles desde las unidades en cada recálculo. Meterles
mano sería escribir sobre algo que se va a recalcular igual.

## ⚠️ Tampoco toca los ACTUAL

En un presupuesto las disponibles son un supuesto y salen del inventario. En un
ACTUAL son una **medición**: cuántas unidades estuvieron realmente a la venta.
En Ojochal 2025 van de 7,2 a 11,9 por día porque las villas fueron abriendo.
Aplanarlas al inventario de hoy contaría como disponible una villa que todavía
no existía, y la ocupación de un año cerrado bajaría —de 30,8 % a 28,0 %— sin
que se hubiera movido una noche vendida.

Uso:
    python -m scripts.corregir_noches_disponibles            # ensayo
    python -m scripts.corregir_noches_disponibles --aplicar
"""
from __future__ import annotations

import asyncio
import sys
from decimal import Decimal

from sqlalchemy import select

from app.db import SessionLocal
from app.engine.recalculate import _unidades_del_escenario
from app.engine.revenue_calculator import CALENDAR_DAYS
from app.hotel_actual import HOTEL_ID
from app.models.scenario import Scenario
from app.models.scenario_stat import ScenarioStat


async def main(aplicar: bool) -> int:
    async with SessionLocal() as db:
        escenarios = (await db.execute(select(Scenario).where(
            Scenario.hotel_id == HOTEL_ID))).scalars().all()
        tocados = 0
        for esc in sorted(escenarios, key=lambda s: (s.year, s.version)):
            modo = getattr(esc, "revenue_source", "drivers")
            if modo != "checkbook":
                continue
            if (getattr(esc, "type", "") or "").upper() == "ACTUAL":
                print(f"  · {esc.year} {esc.type:<9} {esc.version:<26} "
                      f"ACTUAL: lo medido no se toca")
                continue
            unidades = await _unidades_del_escenario(db, esc)
            stats = {s.month: s for s in (await db.execute(select(ScenarioStat).where(
                ScenarioStat.scenario_id == esc.id))).scalars().all()}
            if not stats:
                print(f"  {esc.year} {esc.type} {esc.version}: sin estadísticas, se salta")
                continue

            antes = sum(int(s.rooms_available or 0) for s in stats.values())
            despues = 0
            cambios = 0
            for mes, st in stats.items():
                if not 1 <= int(mes) <= 12:
                    continue
                nuevo = unidades * CALENDAR_DAYS[int(mes) - 1]
                despues += nuevo
                if int(st.rooms_available or 0) != nuevo:
                    cambios += 1
                    st.rooms_available = nuevo
                    ocup = Decimal(str(st.rooms_occupied or 0))
                    st.occupancy_pct = (ocup / Decimal(nuevo)) if nuevo else Decimal("0")

            ocupadas = sum(Decimal(str(s.rooms_occupied or 0)) for s in stats.values())
            o_antes = (ocupadas / antes * 100) if antes else 0
            o_desp = (ocupadas / despues * 100) if despues else 0
            marca = "·" if not cambios else "→"
            print(f"  {marca} {esc.year} {esc.type:<9} {esc.version:<26} "
                  f"unidades={unidades:>3}  "
                  f"disp {antes:>6,} → {despues:>6,}   "
                  f"ocupación {float(o_antes):>5.1f}% → {float(o_desp):>5.1f}%   "
                  f"({cambios} meses)")
            tocados += cambios

        if not aplicar:
            await db.rollback()
            print(f"\nENSAYO: {tocados} meses cambiarían. Nada se guardó.")
            return 0
        await db.commit()
        print(f"\n✓ Guardado: {tocados} meses corregidos.")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main("--aplicar" in sys.argv)))
