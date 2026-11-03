# -*- coding: utf-8 -*-
"""Saca de FinPlan los datos del libro de ingresos accesorios. Sólo LEE.

Owner, 2026-11-02, mostrando `Oxygen_Ingresos_Accesorios_2027.xlsx`: *«podés
hacer este mismo formato para Ojochal Garden»*.

El FORMATO es el de Oxygen; las LÍNEAS son las de esta propiedad. No se copian
las de allá: Ojochal factura su restaurante en `REV_SABOR_OJOCHAL` y no tiene
Beverage ni Laundry a huéspedes. Un libro con las pestañas de otro hotel sería
nueve tabs vacíos y dos que importan.

Imprime JSON por salida estándar para que el armador del .xlsx corra afuera:
el contenedor no tiene de dónde bajar el archivo.

Uso:
    python -m scripts.datos_ingresos_accesorios 2025 2026 2027 > datos.json
"""
from __future__ import annotations

import asyncio
import json
import sys
from decimal import Decimal

from sqlalchemy import select

from app.api import pl_api
from app.db import SessionLocal
from app.hotel_actual import HOTEL_ID, HOTEL_NAME
from app.models.canal_rooms import CanalRoomsEntry, CanalSegmento
from app.models.scenario import Scenario
from app.models.scenario_stat import ScenarioStat

D = lambda v: Decimal(str(v or 0))
f = lambda v: float(D(v))

#: Lo que NO es accesorio: es la línea que el libro acompaña.
ROOMS = {"REV_ROOMS", "REV_ROOMS_OTHER"}


async def _de_un_escenario(db, esc) -> dict:
    """Todo lo que el libro necesita de un escenario: KPIs y líneas, por mes."""
    stats = {int(s.month): s for s in (await db.execute(select(ScenarioStat).where(
        ScenarioStat.scenario_id == esc.id))).scalars()}

    # Las noches de CORTESÍA, si el escenario usa el modelo por segmento. Ocupan
    # villa y no cobran: el ADR las excluye y el libro tiene que poder decirlo.
    no_cobran = {s.code for s in (await db.execute(select(CanalSegmento).where(
        CanalSegmento.hotel_id == HOTEL_ID,
        CanalSegmento.genera_ingreso.is_(False)))).scalars()}
    cortesia = {m: 0.0 for m in range(1, 13)}
    for e in (await db.execute(select(CanalRoomsEntry).where(
            CanalRoomsEntry.scenario_id == esc.id))).scalars():
        if e.segmento_code in no_cobran:
            cortesia[int(e.month)] = cortesia.get(int(e.month), 0.0) + f(e.noches)

    mensual = await pl_api._monthly_results(db, esc)
    lineas: dict[str, dict] = {}
    for m in mensual:
        for ln in m["lines"]:
            if not ln.line_code.startswith("REV"):
                continue
            d = lineas.setdefault(ln.line_code, {"nombre": "", "meses": [0.0] * 12})
            d["meses"][m["month"] - 1] += f(ln.amount_usd)
    anual = pl_api._aggregate(mensual, 12)
    for ln in anual["lines"]:
        if ln["line_code"] in lineas:
            lineas[ln["line_code"]]["nombre"] = ln["line_name"]

    meses = []
    for m in range(1, 13):
        st = stats.get(m)
        meses.append({
            "mes": m,
            "disponibles": int(getattr(st, "rooms_available", 0) or 0) if st else 0,
            "ocupadas": f(getattr(st, "rooms_occupied", 0)) if st else 0.0,
            "cortesia": cortesia.get(m, 0.0),
            "pax": f(getattr(st, "guests", 0)) if st else 0.0,
        })
    return {
        "id": esc.id, "year": esc.year, "type": esc.type, "version": esc.version,
        "actuals_through": getattr(esc, "actuals_through", 0) or 0,
        "rooms_source": getattr(esc, "rooms_source", "tarifas"),
        "meses": meses,
        "lineas": lineas,
    }


async def main(anios: list[int]) -> int:
    async with SessionLocal() as db:
        todos = (await db.execute(select(Scenario).where(
            Scenario.hotel_id == HOTEL_ID))).scalars().all()
        fuera = {"hotel_id": HOTEL_ID, "hotel_name": HOTEL_NAME,
                 "escenarios": []}
        for a in anios:
            # Para un año pasado manda el ACTUAL; para el que se presupuesta,
            # el BUDGET. Elegir al revés compararía un presupuesto viejo contra
            # uno nuevo y el libro diría «real» sobre algo que nunca pasó.
            cand = [s for s in todos if s.year == a and s.type == "ACTUAL"]
            if not cand:
                cand = [s for s in todos if s.year == a and s.type == "BUDGET"]
            if not cand:
                print(f"# sin escenario para {a}", file=sys.stderr)
                continue
            esc = sorted(cand, key=lambda s: s.created_at or 0)[-1]
            fuera["escenarios"].append(await _de_un_escenario(db, esc))
        print(json.dumps(fuera, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    anios = [int(a) for a in sys.argv[1:]] or [2025, 2026, 2027]
    raise SystemExit(asyncio.run(main(anios)))
