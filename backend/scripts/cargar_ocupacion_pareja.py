# -*- coding: utf-8 -*-
"""Pone el mismo % de ocupación en TODOS los tipos de habitación, mes a mes.

Owner, 2026-10-28, pegando su cuadro de doce porcentajes: *«podés colocarme esa
ocupación acá»* · *«igual para todas las unidades por mes»*.

## Por qué un script y no la pantalla

La pantalla pide el porcentaje **por tipo de habitación**: siete filas × doce
meses, 84 celdas. Cuando el owner tiene un solo porcentaje por mes —que es el
caso cuando sale de un presupuesto de ventas y no de un análisis por villa—
teclear la misma cifra siete veces es donde se cuela el dedo.

## ⚠️ Usa el MISMO endpoint que el botón Guardar

`bulk_occupancy_pct`, no un `INSERT` a mano. Así las noches ocupadas se derivan
con la fórmula de siempre —`pct × unidades × días`, y cero en los meses
cerrados— en vez de con una cuenta paralela que mañana no coincide con la
pantalla.

## ⚠️ Esto NO mueve el P&L si el escenario está en el modelo por segmento

Con `rooms_source = 'canales'`, Rooms sale del tarifario RAC y esta pantalla es
sólo un supuesto cargado al lado. El script lo dice al terminar, para que nadie
cargue doce porcentajes esperando ver moverse el reporte.

Uso:
    python -m scripts.cargar_ocupacion_pareja "BUDGET Working 2027" \
        69.8 90.3 71.8 54.5 44.3 50.9 53.7 58.7 24.5 23.8 38.8 63.0
    ... --aplicar
"""
from __future__ import annotations

import asyncio
import sys
from decimal import Decimal

from sqlalchemy import select

from app.api.revenue_api import OccPctRow, bulk_occupancy_pct
from app.db import SessionLocal
from app.hotel_actual import HOTEL_ID
from app.models.room_type_config import RoomTypeConfig
from app.models.scenario import Scenario

MES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
       "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
COL = ["jan", "feb", "mar", "apr", "may", "jun",
       "jul", "aug", "sep", "oct", "nov", "dec"]
#: El mismo calendario del motor. Contar los días distinto acá daría noches
#: ocupadas que la pantalla no reproduce.
DIAS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


async def main(nombre: str, pcts: list[str], aplicar: bool) -> int:
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
        print(f"escenario: {esc.type} {esc.version} {esc.year}")
        if esc.is_locked:
            print("✗ Enllavado. No se toca.")
            return 2

        # Se acepta «69.8» o «0.698»: el owner copia de un cuadro que muestra
        # porcentajes, y exigirle la fracción es una fuente de errores de 100x.
        fracs = []
        for p in pcts:
            v = Decimal(str(p).replace("%", "").replace(",", ".").strip())
            if v > 1:
                v = v / Decimal("100")
            if not (Decimal("0") <= v <= Decimal("1")):
                print(f"✗ «{p}» no es una ocupación válida (0 a 100 %).")
                return 2
            fracs.append(v)

        tipos = (await db.execute(select(RoomTypeConfig).where(
            RoomTypeConfig.hotel_id == HOTEL_ID,
            RoomTypeConfig.active.is_(True)).order_by(
            RoomTypeConfig.sort_order))).scalars().all()
        unidades = sum(int(t.units or 0) for t in tipos)
        print(f"tipos activos: {len(tipos)}   unidades: {unidades}")

        print("\n  mes      %     noches   de")
        tn = td = Decimal("0")
        for i, f in enumerate(fracs):
            disp = Decimal(unidades * DIAS[i])
            n = (f * disp).quantize(Decimal("0.1"))
            tn += n
            td += disp
            print(f"  {MES[i]}   {float(f)*100:>6.1f}%  {float(n):>8.1f}  de {int(disp):>5}")
        print(f"  AÑO    {float(tn/td)*100:>6.1f}%  {float(tn):>8.1f}  de {int(td):>5}")

        if not aplicar:
            print("\nENSAYO: nada se guardó.")
            return 0

        filas = [OccPctRow(room_type_id=t.id,
                           **{c: f for c, f in zip(COL, fracs)})
                 for t in tipos]
        r = await bulk_occupancy_pct(esc.id, filas, db)
        print(f"\n✓ Guardado: {r['saved']} tipos × 12 meses.")
        if getattr(esc, "rooms_source", "tarifas") == "canales":
            print("⚠ Este escenario saca Rooms del modelo por segmento: lo que "
                  "se acaba de cargar NO mueve el P&L.")
        return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--aplicar"]
    if len(args) != 13:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(
        main(args[0], args[1:], "--aplicar" in sys.argv)))
