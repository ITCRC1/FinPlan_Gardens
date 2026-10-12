# -*- coding: utf-8 -*-
"""Carga el On The Books de Ojochal Gardens — corte de la semana 42 de 2026.

## De dónde sale

Export del PMS del 2026-10-12:
`20261012T133354.025-RESERVAS FUTURAS GARDES 2027 (c).XLS`, 92 reservas.

Se excluyen dos:

* **1467** — tiene `fecha_anulada` 2026-06-04, aunque el estado siga en `Co`.
* **1677** — estado `So`, no `Co`. No es una reserva confirmada.

Quedan **90**, y abarcan del 16-oct-2026 al 10-nov-2027. El archivo se llama
«2027» pero **un tercio son llegadas de 2026**: por eso cada noche se guarda con
SU año real, que es justo lo que `OnTheBooksEntry` pide («el history_forecast
trae horizonte multi-año en el MISMO archivo»).

## Cómo se reparte la plata

Verificado en las 92 filas, sin una sola excepción:

    importe_total  ==  precio_hab × noches  +  carg_aut

* `precio_hab` es el cargo de HABITACIONES por noche de toda la reserva (no por
  habitación: la reserva 1340 trae 8 habitaciones y un solo `precio_hab`).
* `carg_aut` son cargos automáticos, **no son ingreso de habitaciones**. Van
  enteros en la noche de llegada.

De ahí sale la misma separación que hace el importador de Opera entre
`full_revenue` y `only_rooms`:

    rooms_revenue = precio_hab × noches        →  97,871.61
    total_revenue = rooms_revenue + carg_aut   →  99,428.11

## Qué escribe

* `otb_daily_occ` — 154 celdas (año, mes, día) con `rooms_sold`.
* `on_the_books_entries` — 12 filas (año, mes) con revenue, rooms y pax.

⚠️ **La llave es el HOTEL, no el escenario.** El `scenario_id` es RASTRO: dice
desde dónde se subió y nada más. Borrar ese escenario no se lleva las reservas.

⚠️ **Reemplaza SOLO la semana 42**, igual que `import-otb-xml`. Las demás
semanas son el historial de pace y no se tocan.

## Cómo se corre

    python -m scripts.cargar_otb_semana42              # simula
    python -m scripts.cargar_otb_semana42 --aplicar    # escribe

Todo en UNA transacción, con la verificación adentro: si lo escrito no cuadra
contra el archivo, hace rollback y no queda nada.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

HOTEL = "OJO"
#: El export es del 2026-10-12 → semana ISO 42.
SEMANA = 42
#: Rastro, no dueño: BUDGET Working 2027.
RASTRO = "cbe61209-d487-4f4f-a37b-f9e82da191bf"

DATOS = pathlib.Path(__file__).parent / "datos" / "otb_ojo_semana42_2026.json"

#: Lo que el archivo dice, para comparar DESPUÉS de escribir. No se recalcula
#: desde lo insertado: eso solo probaría que la suma sabe sumar.
ESPERADO = {"dias": 154, "meses": 12, "room_nights": 501,
            "rooms_revenue": 97871.61, "total_revenue": 99428.11}


async def main(aplicar: bool) -> int:
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import delete as sa_delete, func, select
    from app.db import SessionLocal
    from app.models.on_the_books import OnTheBooksEntry
    from app.models.otb_daily_occ import OtbDailyOcc

    agg = json.loads(DATOS.read_text(encoding="utf-8"))
    dia, mes = agg["dia"], agg["mes"]

    async with SessionLocal() as db:
        async def cuenta(M):
            return (await db.execute(select(func.count()).select_from(M).where(
                M.hotel_id == HOTEL, M.week == SEMANA))).scalar() or 0

        print(f"  hotel {HOTEL} · semana {SEMANA}")
        print(f"  hay hoy:            {await cuenta(OtbDailyOcc):>4} diarias, "
              f"{await cuenta(OnTheBooksEntry):>3} mensuales")
        print(f"  se van a escribir:  {len(dia):>4} diarias, {len(mes):>3} mensuales")
        for k, v in ESPERADO.items():
            print(f"     {k:<16} {v:>12,.2f}" if isinstance(v, float)
                  else f"     {k:<16} {v:>12}")

        if not aplicar:
            print("\n  (simulación: no se escribió nada. Agregá --aplicar)")
            return 0

        # Reemplazo completo de la foto de ESTA semana.
        await db.execute(sa_delete(OtbDailyOcc).where(
            OtbDailyOcc.hotel_id == HOTEL, OtbDailyOcc.week == SEMANA))
        await db.execute(sa_delete(OnTheBooksEntry).where(
            OnTheBooksEntry.hotel_id == HOTEL, OnTheBooksEntry.week == SEMANA))

        for k, v in dia.items():
            y, m, d = (int(x) for x in k.split("-"))
            db.add(OtbDailyOcc(id=str(uuid.uuid4()), hotel_id=HOTEL,
                               scenario_id=RASTRO, week=SEMANA, year=y, month=m,
                               day=d, rooms_sold=round(v["rooms"], 2)))
        for k, v in mes.items():
            y, m = (int(x) for x in k.split("-"))
            db.add(OnTheBooksEntry(id=str(uuid.uuid4()), hotel_id=HOTEL,
                                   scenario_id=RASTRO, week=SEMANA, year=y, month=m,
                                   total_revenue=round(v["tr"], 2),
                                   rooms_revenue=round(v["rr"], 2),
                                   rooms_occupied=round(v["rooms"], 2),
                                   guests=round(v["gu"], 2)))
        await db.flush()

        # ── La verificación, ANTES de confirmar ─────────────────────────────
        async def suma(M, col):
            return float((await db.execute(select(func.coalesce(func.sum(col), 0))
                .where(M.hotel_id == HOTEL, M.week == SEMANA))).scalar() or 0)

        leido = {
            "dias": await cuenta(OtbDailyOcc),
            "meses": await cuenta(OnTheBooksEntry),
            "room_nights": await suma(OnTheBooksEntry, OnTheBooksEntry.rooms_occupied),
            "rooms_revenue": await suma(OnTheBooksEntry, OnTheBooksEntry.rooms_revenue),
            "total_revenue": await suma(OnTheBooksEntry, OnTheBooksEntry.total_revenue),
        }
        fallos = [f"{k}: quedó {leido[k]:,.2f} y el archivo dice {v:,.2f}"
                  for k, v in ESPERADO.items() if abs(leido[k] - v) > 0.05]
        # Las noches del diario tienen que dar lo mismo que las del mensual.
        noches_diario = await suma(OtbDailyOcc, OtbDailyOcc.rooms_sold)
        if abs(noches_diario - ESPERADO["room_nights"]) > 0.05:
            fallos.append(f"el diario suma {noches_diario:,.2f} noches y el "
                          f"mensual {ESPERADO['room_nights']:,.2f}")
        if fallos:
            await db.rollback()
            print("\n  SE DESHIZO TODO. No se escribió nada:")
            for f in fallos:
                print(f"    X {f}")
            return 1

        await db.commit()
        print(f"\n  LISTO. {leido['dias']} diarias · {leido['meses']} mensuales · "
              f"{leido['room_nights']:,.0f} room-nights · "
              f"rooms {leido['rooms_revenue']:,.2f} · total {leido['total_revenue']:,.2f}")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main("--aplicar" in sys.argv)))
