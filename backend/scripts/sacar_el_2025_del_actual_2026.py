# -*- coding: utf-8 -*-
"""Saca de ACTUAL 2026 los meses de 2025 que quedaron en agosto-diciembre.

## Que paso (2026-10-08)

El archivo `..._ACTUAL_Final_2025_full.xlsx` —bloque «Actual Final 2025»— se
subio con **ACTUAL Final 2026** elegido en el selector. Los doce meses de 2025
quedaron guardados como 2026.

Despues se subio el detalle real de 2026, que trae **enero a julio**. La carga
es `merge=true`: reemplaza SOLO los meses que vienen en el archivo. Asi que
enero-julio quedaron bien y **agosto-diciembre siguieron siendo 2025**.

Medido contra ACTUAL 2025, identico al centavo en las cinco tablas:

    actual_entries             184,022.53     opex_entries      48,649.29
    revenue_account_entries     82,588.09     belowgop_...      16,195.92
    cost_entries                 4,454.17     payroll (8-12)    32,135.07

Y las estadisticas: 308/98, 326/56, 363/49, 329/80, 369/155 — calcadas.

**Nada fallo, otra vez.** El P&L cuadra consigo mismo porque esos cinco meses
son internamente coherentes: son un año de verdad, solo que el año equivocado.

El agujero que lo dejo entrar ya esta tapado (`gl.ano_no_coincide`).

## Que toca y que NO

**Toca**, y solo en ACTUAL 2026:

* `actual_entries`, `revenue_account_entries`, `opex_entries`, `cost_entries`,
  `belowgop_account_entries` → pone en **cero** las columnas `aug..dec`.
  No borra la fila: enero-julio de esa misma fila es dato bueno de 2026.
* `payroll_concept_entries`, `scenario_stats`, `actual_pl_lines` → **borra** las
  filas de mes >= 8. En estas tablas la fila ES el mes.

**NO toca:**

* **Enero a julio del ACTUAL 2026.** Es el dato real de 2026, recien subido. El
  script lo mide antes y despues y aborta si cambio un centavo.
* **ACTUAL 2025.** Igual: medido antes y despues.
* **`payroll_positions`.** Son las posiciones sinteticas `(Actual GL)`, con FTE
  en cero; aportan costo via `payroll_concept_entries`, no headcount. Borrarlas
  dejaria a enero-julio sin a quien colgar su planilla.
* **Los 12 tipos de cambio del 2026.** Son del 2026 y no vinieron del archivo.
* **FORECAST Working 2026.** Su agosto-diciembre se cargo aparte y esta bien
  ($86,254.43). Sus meses cerrados (1-7) no los guarda: los espeja del ACTUAL
  2026 —ver `engine/meses_cerrados.py`—, asi que se arreglan solos con esto.

## Como se corre

    python -m scripts.sacar_el_2025_del_actual_2026              # simula
    python -m scripts.sacar_el_2025_del_actual_2026 --aplicar    # escribe

Todo en UNA transaccion: o sale entero o no sale.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

#: Fijos a proposito: un script que borra no elige su objetivo por nombre,
#: porque un nombre se repite y un id no.
AC_2025 = "21e052d9-29de-49c7-9c9a-189bdfb60fae"
AC_2026 = "49dfca0d-acce-4190-8d4b-aebedc818d40"

MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]
#: Lo que sobro del 2025. Agosto = mes 8.
DESDE = 8
TARDE = MESES[DESDE - 1:]
TEMPRANO = MESES[:DESDE - 1]


def _por_columna():
    """Tablas donde el mes es una COLUMNA: se ponen en cero, no se borra la fila."""
    from app.models.actual_entry import ActualEntry
    from app.models.belowgop_account_entry import BelowGopAccountEntry
    from app.models.cost_entry import CostEntry
    from app.models.opex_entry import OpexEntry
    from app.models.revenue_account_entry import RevenueAccountEntry
    return [ActualEntry, RevenueAccountEntry, OpexEntry, CostEntry,
            BelowGopAccountEntry]


def _por_fila():
    """Tablas donde la fila ES el mes: se borran las de mes >= DESDE."""
    from app.models.actual_pl_line import ActualPLLine
    from app.models.payroll_concept_entry import PayrollConceptEntry
    from app.models.scenario_stat import ScenarioStat
    return [PayrollConceptEntry, ScenarioStat, ActualPLLine]


async def _suma(db, M, sid: str, meses: list[str]) -> float:
    """Lo que suman esas columnas de mes en ese escenario."""
    from sqlalchemy import func, select
    cols = [getattr(M, m) for m in meses if hasattr(M, m)]
    if not cols:
        return 0.0
    expr = func.coalesce(cols[0], 0)
    for c in cols[1:]:
        expr = expr + func.coalesce(c, 0)
    v = (await db.execute(select(func.coalesce(func.sum(expr), 0))
                          .where(M.scenario_id == sid))).scalar()
    return float(v or 0)


async def _filas_por_mes(db, M, sid: str) -> dict[int, int]:
    from sqlalchemy import func, select
    res = await db.execute(select(M.month, func.count()).where(
        M.scenario_id == sid).group_by(M.month))
    return {m: n for m, n in res.all()}


async def main(aplicar: bool) -> int:
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import delete as sa_delete, select, update as sa_update
    from app.db import SessionLocal
    from app.models.scenario import Scenario

    col_models, fila_models = _por_columna(), _por_fila()

    async with SessionLocal() as db:
        escen = {s.id: s for s in (await db.execute(select(Scenario).where(
            Scenario.id.in_([AC_2025, AC_2026])))).scalars()}
        for sid, etq in ((AC_2025, "ACTUAL 2025"), (AC_2026, "ACTUAL 2026")):
            if sid not in escen:
                print(f"  X no existe {etq} ({sid})")
                return 1
            s = escen[sid]
            print(f"  {etq}: {s.type} {s.version} {s.year}")

        # ── Foto de antes ───────────────────────────────────────────────────
        antes = {}
        for M in col_models:
            antes[M] = {
                "tarde26": await _suma(db, M, AC_2026, TARDE),
                "temp26": await _suma(db, M, AC_2026, TEMPRANO),
                "tarde25": await _suma(db, M, AC_2025, TARDE),
                "temp25": await _suma(db, M, AC_2025, TEMPRANO),
            }
        filas = {M: (await _filas_por_mes(db, M, AC_2026)) for M in fila_models}
        filas25 = {M: (await _filas_por_mes(db, M, AC_2025)) for M in fila_models}

        print(f"\n{'tabla':<30}{'ago-dic 2026':>16}{'es 2025?':>14}"
              f"{'ene-jul 2026':>16}")
        print("=" * 78)
        for M in col_models:
            a = antes[M]
            igual = "SI" if abs(a["tarde26"] - a["tarde25"]) < 0.01 else "distinto"
            print(f"  {M.__tablename__:<28}{a['tarde26']:>16,.2f}{igual:>14}"
                  f"{a['temp26']:>16,.2f}")
        for M in fila_models:
            n = sum(v for m, v in filas[M].items() if m >= DESDE)
            n25 = sum(v for m, v in filas25[M].items() if m >= DESDE)
            keep = sum(v for m, v in filas[M].items() if m < DESDE)
            if n or keep:
                igual = "SI" if n == n25 else "distinto"
                print(f"  {M.__tablename__:<28}{n:>10} filas{igual:>14}"
                      f"{keep:>10} filas")

        tocar = (sum(1 for M in col_models if abs(antes[M]["tarde26"]) > 0.01)
                 + sum(1 for M in fila_models
                       if any(m >= DESDE for m in filas[M])))
        if not tocar:
            print("\nACTUAL 2026 ya esta limpio de agosto a diciembre.")
            return 0
        if not aplicar:
            print("\n(simulacion: no se escribio nada. Agregá --aplicar para hacerlo)")
            return 0

        # ── Escribir ────────────────────────────────────────────────────────
        print()
        for M in col_models:
            vals = {m: 0 for m in TARDE if hasattr(M, m)}
            await db.execute(sa_update(M).where(M.scenario_id == AC_2026).values(**vals))
            print(f"  {M.__tablename__:<28} ago-dic -> 0")
        for M in fila_models:
            n = sum(v for m, v in filas[M].items() if m >= DESDE)
            if n:
                await db.execute(sa_delete(M).where(
                    M.scenario_id == AC_2026, M.month >= DESDE))
                print(f"  {M.__tablename__:<28} -{n} filas (mes >= {DESDE})")

        # ── La baranda: enero-julio y el 2025 no se movieron ────────────────
        fallos = []
        for M in col_models:
            a = antes[M]
            t26 = await _suma(db, M, AC_2026, TARDE)
            e26 = await _suma(db, M, AC_2026, TEMPRANO)
            t25 = await _suma(db, M, AC_2025, TARDE)
            e25 = await _suma(db, M, AC_2025, TEMPRANO)
            if abs(t26) > 0.01:
                fallos.append(f"{M.__tablename__}: ago-dic 2026 quedo en {t26:,.2f}")
            if abs(e26 - a["temp26"]) > 0.01:
                fallos.append(f"{M.__tablename__}: ENE-JUL 2026 cambio "
                              f"{a['temp26']:,.2f} -> {e26:,.2f}")
            if abs(t25 - a["tarde25"]) > 0.01 or abs(e25 - a["temp25"]) > 0.01:
                fallos.append(f"{M.__tablename__}: ACTUAL 2025 cambio")
        for M in fila_models:
            ahora = await _filas_por_mes(db, M, AC_2026)
            if any(m >= DESDE for m in ahora):
                fallos.append(f"{M.__tablename__}: quedaron filas de mes >= {DESDE}")
            for m, n in filas[M].items():
                if m < DESDE and ahora.get(m, 0) != n:
                    fallos.append(f"{M.__tablename__}: mes {m} de 2026 cambio "
                                  f"{n} -> {ahora.get(m, 0)}")
            if (await _filas_por_mes(db, M, AC_2025)) != filas25[M]:
                fallos.append(f"{M.__tablename__}: ACTUAL 2025 cambio")

        if fallos:
            await db.rollback()
            print("\nSE DESHIZO TODO. No se escribio nada:")
            for f in fallos:
                print(f"  X {f}")
            return 1

        await db.commit()
        print("\nLISTO. Enero-julio del ACTUAL 2026, intacto:")
        for M in col_models:
            print(f"  {M.__tablename__:<28}{antes[M]['temp26']:>16,.2f}")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main("--aplicar" in sys.argv)))
