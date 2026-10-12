# -*- coding: utf-8 -*-
"""Country Mix y Channel Mix de Ojochal Gardens, del mismo export del PMS.

Fuente: `20261012T133354.025-RESERVAS FUTURAS GARDES 2027 (c).XLS`, las mismas
90 reservas confirmadas que ya alimentaron el On The Books
(`cargar_otb_semana42.py`). Cada noche cuenta en su mes y su año reales.

## El mapeo de segmentos, y de dónde salió

El PMS trae `desc_segmerc`; `market_codes` tiene los códigos canónicos. El
puente NO se hizo por parecido de nombre sino cruzando cada segmento contra las
AGENCIAS que lo usan:

    3.1 TRAVEL AGENCIES – FIT  (49)  CR Découverte, Bella Aventura, Asuaire…  → TAFIT
    1.1 DIRECT – TRANSIENT     (15)  DIRECTOS                                 → DIR
    5.1 OTA – TRANSIENT        (12)  Booking.com, Simple Booking              → OTA
    RESONLINE NO BORRAR        (12)  Booking.com, OTS Globe, Expedia          → OTA
    DIRECTAS                    (1)  DIRECTOS                                 → DIR
    CPL                         (1)  CPL, importe 0                           → COM

⚠️ «RESONLINE NO BORRAR» es un recordatorio interno convertido en nombre de
segmento. Por el nombre no se sabe qué es; por sus agencias, sí: las tres son
OTAs. Si algún día deja de serlo, este mapeo miente en silencio.

## A qué escenario va cada año

Estas tres tablas llevan `month` pero NO `year`: la llave es el escenario. Así
que el año decide a cuál va.

    llegadas 2026  →  FORECAST Working 2026
    llegadas 2027  →  BUDGET   Working 2027

## Qué escribe

* `country_mix_entries`  — país × mes × métrica (rooms, pax)
* `channel_mix_entries`  — canal canónico × mes × métrica
* `channel_mix_detail`   — código de market × mes × métrica

`origen='xml'`, que es como el modelo marca lo que vino del PMS frente a lo
corregido a mano. Las tres vistas reconcilian a 501 room-nights y 1.152 pax, y
eso se verifica ADENTRO de la transacción.

## Cómo se corre

    python -m scripts.cargar_mix_semana42              # simula
    python -m scripts.cargar_mix_semana42 --aplicar    # escribe
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import uuid
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

ESCENARIO = {
    2026: "341c5b66-1e98-4b97-93fc-ce924583582b",   # FORECAST Working 2026
    2027: "cbe61209-d487-4f4f-a37b-f9e82da191bf",   # BUDGET   Working 2027
}
DATOS = pathlib.Path(__file__).parent / "datos" / "mix_ojo_semana42_2026.json"

#: Lo que dice el ARCHIVO. Se compara contra esto, no contra lo recién escrito.
ESPERADO = {"rooms": 501.0, "pax": 1152.0}


def _partes(k: str):
    y, m, clave, metrica = k.split("|")
    return int(y), int(m), clave, metrica


async def main(aplicar: bool) -> int:
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import delete as sa_delete, func, select
    from app.db import SessionLocal
    from app.models.channel_mix import ChannelMixDetail, ChannelMixEntry
    from app.models.country_mix import CountryMixEntry

    datos = json.loads(DATOS.read_text(encoding="utf-8"))
    #: (modelo, clave del JSON, nombre de la columna que lleva la clave)
    PLAN = [(CountryMixEntry, "pais", "country"),
            (ChannelMixEntry, "canal", "channel"),
            (ChannelMixDetail, "detalle", "market_code")]

    async with SessionLocal() as db:
        print("  destino por año:")
        for anio, sid in ESCENARIO.items():
            from app.models.scenario import Scenario
            s = await db.get(Scenario, sid)
            if s is None:
                print(f"    X no existe el escenario de {anio} ({sid})")
                return 1
            print(f"    {anio} -> {s.type} {s.version} {s.year}")

        print("\n  tabla                      filas   hay hoy")
        for M, clave, _col in PLAN:
            hay = (await db.execute(select(func.count()).select_from(M).where(
                M.scenario_id.in_(list(ESCENARIO.values()))))).scalar() or 0
            print(f"    {M.__tablename__:<24}{len(datos[clave]):>6}{hay:>10}")
        for met, esp in ESPERADO.items():
            print(f"    control {met:<16}{esp:>10,.0f}")

        if not aplicar:
            print("\n  (simulación: no se escribió nada. Agregá --aplicar)")
            return 0

        for M, clave, col in PLAN:
            await db.execute(sa_delete(M).where(
                M.scenario_id.in_(list(ESCENARIO.values()))))
            for k, val in datos[clave].items():
                y, m, nombre, met = _partes(k)
                db.add(M(id=str(uuid.uuid4()), scenario_id=ESCENARIO[y], month=m,
                         metric=met, value=Decimal(str(round(val, 2))),
                         origen="xml", **{col: nombre}))
        await db.flush()

        # ── La verificación, antes de confirmar ─────────────────────────────
        fallos = []
        for M, clave, _col in PLAN:
            for met, esp in ESPERADO.items():
                got = float((await db.execute(
                    select(func.coalesce(func.sum(M.value), 0)).where(
                        M.scenario_id.in_(list(ESCENARIO.values())),
                        M.metric == met))).scalar() or 0)
                if abs(got - esp) > 0.05:
                    fallos.append(f"{M.__tablename__}/{met}: {got:,.2f} != {esp:,.2f}")
            n = (await db.execute(select(func.count()).select_from(M).where(
                M.scenario_id.in_(list(ESCENARIO.values()))))).scalar() or 0
            if n != len(datos[clave]):
                fallos.append(f"{M.__tablename__}: {n} filas != {len(datos[clave])}")
        if fallos:
            await db.rollback()
            print("\n  SE DESHIZO TODO. No se escribió nada:")
            for f in fallos:
                print(f"    X {f}")
            return 1

        await db.commit()
        print("\n  LISTO. Las tres vistas cuadran en 501 room-nights y 1.152 pax.")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main("--aplicar" in sys.argv)))
