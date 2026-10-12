# -*- coding: utf-8 -*-
"""Saca de FinPlan Gardens el On The Books y los mixes que no iban acá.

## Qué pasó (2026-10-12)

El owner mandó el export de reservas futuras del PMS y pidió cargarlo. Se cargó
**en FinPlan**, y la pregunta que faltó hacer era otra: *«¿va a FinPlan?»*.

Owner: *«esto no era aca»* · *«no era en este app finplan Garden»* · *«era en
ExperienceOS garden»*.

Los datos no están mal —son las reservas reales de Ojochal— pero son de otro
sistema. Ahí tienen su propio camino: `POST /admin/import/stays`, con plantilla,
dry-run, transacción todo-o-nada y auditoría, que escribe `guest_stays` con
`source='FILE'`.

## Qué borra

Lo que escribieron `cargar_otb_semana42.py` y `cargar_mix_semana42.py`, y nada
más:

    on_the_books_entries   hotel OJO, semana 42          12
    otb_daily_occ          hotel OJO, semana 42         154
    country_mix_entries    FORECAST 2026 + BUDGET 2027   84
    channel_mix_entries    FORECAST 2026 + BUDGET 2027   50
    channel_mix_detail     FORECAST 2026 + BUDGET 2027   52
                                                       ---
                                                        352

Las cinco tablas estaban **vacías** antes de la carga —medido— así que no hay
nada anterior que esto pueda llevarse por delante. Se verifica que queden en
cero ANTES de confirmar.

⚠️ **Las otras semanas y los demás escenarios no se tocan.** Hoy no hay nada
más en esas tablas, pero el filtro es explícito igual: si mañana alguien carga
la semana 43, este script sigue borrando solo la 42.

## Cómo se corre

    python -m scripts.sacar_el_otb_que_no_iba_aca              # simula
    python -m scripts.sacar_el_otb_que_no_iba_aca --aplicar    # borra
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

HOTEL = "OJO"
SEMANA = 42
ESCENARIOS = [
    "341c5b66-1e98-4b97-93fc-ce924583582b",   # FORECAST Working 2026
    "cbe61209-d487-4f4f-a37b-f9e82da191bf",   # BUDGET   Working 2027
]


async def main(aplicar: bool) -> int:
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import delete as sa_delete, func, select
    from app.db import SessionLocal
    from app.models.channel_mix import ChannelMixDetail, ChannelMixEntry
    from app.models.country_mix import CountryMixEntry
    from app.models.on_the_books import OnTheBooksEntry
    from app.models.otb_daily_occ import OtbDailyOcc

    #: (modelo, condición). Cada una dice EXACTAMENTE qué se lleva.
    POR_HOTEL = [OnTheBooksEntry, OtbDailyOcc]
    POR_ESCENARIO = [CountryMixEntry, ChannelMixEntry, ChannelMixDetail]

    async with SessionLocal() as db:
        def cond(M):
            return ((M.hotel_id == HOTEL, M.week == SEMANA) if M in POR_HOTEL
                    else (M.scenario_id.in_(ESCENARIOS),))

        async def cuenta(M, propio=True):
            c = cond(M) if propio else ()
            q = select(func.count()).select_from(M)
            return (await db.execute(q.where(*c) if c else q)).scalar() or 0

        total = 0
        print(f"  {'tabla':<24}{'a borrar':>10}{'en la tabla':>13}")
        for M in POR_HOTEL + POR_ESCENARIO:
            n, todo = await cuenta(M), await cuenta(M, propio=False)
            total += n
            print(f"    {M.__tablename__:<22}{n:>10}{todo:>13}")
        print(f"    {'TOTAL':<22}{total:>10}")

        if not total:
            print("\n  Ya no hay nada que sacar.")
            return 0
        if not aplicar:
            print("\n  (simulación: no se borró nada. Agregá --aplicar)")
            return 0

        for M in POR_HOTEL + POR_ESCENARIO:
            await db.execute(sa_delete(M).where(*cond(M)))
        await db.flush()

        # ── La baranda: lo propio en cero, y nada ajeno de menos ────────────
        fallos = []
        for M in POR_HOTEL + POR_ESCENARIO:
            queda = await cuenta(M)
            if queda:
                fallos.append(f"{M.__tablename__}: quedaron {queda}")
            sobra = await cuenta(M, propio=False)
            if sobra:
                fallos.append(f"{M.__tablename__}: quedan {sobra} filas AJENAS "
                              f"— revisar antes de confirmar")
        if fallos:
            await db.rollback()
            print("\n  SE DESHIZO TODO. No se borró nada:")
            for f in fallos:
                print(f"    X {f}")
            return 1

        await db.commit()
        print(f"\n  LISTO. {total} filas fuera. Las cinco tablas quedaron vacías, "
              f"como estaban antes de la carga.")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main("--aplicar" in sys.argv)))
