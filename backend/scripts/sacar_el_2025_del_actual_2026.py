# -*- coding: utf-8 -*-
"""Saca de ACTUAL 2026 el ano 2025 que entro por el selector equivocado.

## Que paso (2026-10-08)

El owner subio `Ojochal_Gardens_Detalle_ACTUAL_Final_2025_full.xlsx` —bloque
«Actual Final 2025»— con **ACTUAL Final 2026** elegido en el selector de
version. Los doce meses de 2025 quedaron guardados como 2026:

    13:49:48  ->  ACTUAL 2026   (equivocado)
    14:17:39  ->  ACTUAL 2025   (correcto, y sigue ahi)

**Nada fallo.** El P&L cuadro consigo mismo y la verificacion de arriba contra
el detalle de abajo tambien, porque los dos lados salen del MISMO archivo. Lo
unico que no cuadraba era contra la realidad, y eso el sistema no lo miraba.

El agujero ya esta tapado: `scenarios_api.py` compara el ano del bloque contra
el de la version elegida y se niega antes de escribir una sola fila
(`gl.ano_no_coincide`, sin salida de emergencia). Este script limpia lo que
alcanzo a entrar ANTES de ese arreglo.

## Que borra y que NO

**Borra**, y solo en ACTUAL 2026:

    actual_entries · actual_pl_lines · belowgop_account_entries · cost_entries
    opex_entries · payroll_concept_entries · payroll_positions
    revenue_account_entries · scenario_stats

**NO toca:**

* **ACTUAL 2025** — la carga buena. El script lo mide antes y despues y aborta
  si cambio una sola fila.
* **Los 12 tipos de cambio del 2026.** Son del 2026 y no vinieron del archivo.
* Ningun otro escenario.

Tambien borra la traza de la subida de las 13:49 (`import_files` /
`import_batches` del 2026). El archivo no quedo en el 2026, asi que el registro
no debe decir que si — y dejarlo haria que una carga legitima de ese mismo
archivo al 2026 chocara contra un 409 que ya no aplica.

## Como se corre

    python -m scripts.sacar_el_2025_del_actual_2026              # simula
    python -m scripts.sacar_el_2025_del_actual_2026 --aplicar    # escribe

Todo va en UNA transaccion: o sale entero o no sale.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

#: Los dos escenarios, por id. Fijos a proposito: un script que borra no elige
#: su objetivo por nombre, porque un nombre se repite y un id no.
AC_2025 = "21e052d9-29de-49c7-9c9a-189bdfb60fae"
AC_2026 = "49dfca0d-acce-4190-8d4b-aebedc818d40"

#: La subida equivocada de las 13:49.
FILE_2026 = "db95aeb6-a360-4660-91c6-573e931c6934"


def _modelos():
    from app.models.actual_entry import ActualEntry
    from app.models.actual_pl_line import ActualPLLine
    from app.models.belowgop_account_entry import BelowGopAccountEntry
    from app.models.cost_entry import CostEntry
    from app.models.opex_entry import OpexEntry
    from app.models.payroll_concept_entry import PayrollConceptEntry
    from app.models.payroll_position import PayrollPosition
    from app.models.revenue_account_entry import RevenueAccountEntry
    from app.models.scenario_stat import ScenarioStat
    return [ActualEntry, ActualPLLine, BelowGopAccountEntry, CostEntry,
            OpexEntry, PayrollConceptEntry, PayrollPosition,
            RevenueAccountEntry, ScenarioStat]


async def _foto(db, modelos, sid: str) -> dict[str, int]:
    from sqlalchemy import func, select
    from app.models.exchange_rate import ExchangeRate
    out = {}
    for M in modelos + [ExchangeRate]:
        out[M.__tablename__] = (await db.execute(
            select(func.count()).select_from(M).where(M.scenario_id == sid))).scalar() or 0
    return out


async def main(aplicar: bool) -> int:
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import delete as sa_delete, select
    from app.db import SessionLocal
    from app.models.import_registro import ImportBatch, ImportFile
    from app.models.scenario import Scenario

    modelos = _modelos()

    async with SessionLocal() as db:
        escen = {s.id: s for s in (await db.execute(select(Scenario).where(
            Scenario.id.in_([AC_2025, AC_2026])))).scalars()}
        for sid, etq in ((AC_2025, "ACTUAL 2025"), (AC_2026, "ACTUAL 2026")):
            s = escen.get(sid)
            if s is None:
                print(f"  X no existe el escenario {etq} ({sid})")
                return 1
            print(f"  {etq}: {s.type} {s.version} {s.year}  "
                  f"actuals_through={s.actuals_through}")

        antes25 = await _foto(db, modelos, AC_2025)
        antes26 = await _foto(db, modelos, AC_2026)

        print(f"\n{'tabla':<34}{'2025':>8}{'2026':>8}")
        print("=" * 50)
        for t in sorted(antes26):
            if antes25[t] or antes26[t]:
                print(f"  {t:<32}{antes25[t]:>8}{antes26[t]:>8}")

        a_borrar = sum(antes26[M.__tablename__] for M in modelos)
        if a_borrar == 0:
            print("\nACTUAL 2026 ya esta vacio. No hay nada que hacer.")
            return 0

        print(f"\nSe borrarian {a_borrar} filas de ACTUAL 2026.")
        print(f"Los {antes26['exchange_rates']} tipos de cambio del 2026 NO se tocan.")
        if not aplicar:
            print("\n(simulacion: no se escribio nada. Agregá --aplicar para hacerlo)")
            return 0

        for M in modelos:
            await db.execute(sa_delete(M).where(M.scenario_id == AC_2026))
        # La traza: primero el archivo, despues su lote (hay FK de uno al otro).
        await db.execute(sa_delete(ImportFile).where(ImportFile.id == FILE_2026))
        await db.execute(sa_delete(ImportFile).where(ImportFile.scenario_id == AC_2026))
        await db.execute(sa_delete(ImportBatch).where(ImportBatch.scenario_id == AC_2026))

        # ── La baranda: se mide ANTES de confirmar ──────────────────────────
        #
        # Si el 2025 cambio aunque sea en una fila, se deshace todo. Es el unico
        # dato que no se puede volver a fabricar con un clic.
        desp25 = await _foto(db, modelos, AC_2025)
        desp26 = await _foto(db, modelos, AC_2026)
        fallos = []
        for t, n in antes25.items():
            if desp25[t] != n:
                fallos.append(f"ACTUAL 2025.{t}: {n} -> {desp25[t]}")
        if desp26["exchange_rates"] != antes26["exchange_rates"]:
            fallos.append(f"se tocaron los TC del 2026: "
                          f"{antes26['exchange_rates']} -> {desp26['exchange_rates']}")
        for M in modelos:
            if desp26[M.__tablename__]:
                fallos.append(f"ACTUAL 2026.{M.__tablename__} quedo con "
                              f"{desp26[M.__tablename__]}")
        if fallos:
            await db.rollback()
            print("\nSE DESHIZO TODO. No se escribio nada:")
            for f in fallos:
                print(f"  X {f}")
            return 1

        # El corte del forecast se mueve cuando entra un actual. Si la carga
        # equivocada lo movio, el numero queda mal despues de borrar el dato.
        s26 = escen[AC_2026]
        if s26.actuals_through:
            print(f"\n  ACTUAL 2026 tenia actuals_through={s26.actuals_through} -> 0")
            s26.actuals_through = 0

        await db.commit()
        print(f"\nLISTO. {a_borrar} filas fuera de ACTUAL 2026.")
        print(f"ACTUAL 2025 intacto: "
              f"{sum(desp25[M.__tablename__] for M in modelos)} filas.")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main("--aplicar" in sys.argv)))
