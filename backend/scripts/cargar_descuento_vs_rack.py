# -*- coding: utf-8 -*-
"""Pone el mismo descuento contra rack en todos los segmentos, mes a mes.

Owner, 2026-10-28: *«podemos desconectar los segmentos y poner estos descuentos
en forma manual y editables»*.

«Desconectar los segmentos» no es apagar el modelo: es dejar de diferenciar la
comisión por canal y usar **un solo número por mes**. El modelo ya lo soporta
—la comisión es por segmento y mes— así que esto escribe el mismo valor en los
siete, que es lo mismo que hace la fila «Descuento vs Rack» de la pantalla.

⚠️ **Los de TARIFA PROPIA quedan afuera.** *Long term* no vende contra el
tarifario: un descuento contra rack no significa nada ahí, y aplicárselo le
bajaría el ingreso sin que nadie lo hubiera pedido.

Uso:
    python -m scripts.cargar_descuento_vs_rack "BUDGET Working 2027" \
        13.6 16.1 15.8 15.1 14.4 13.5 17.0 15.2 18.3 17.1 14.3 18.0
    ... --aplicar
"""
from __future__ import annotations

import asyncio
import sys
from decimal import Decimal

from sqlalchemy import select

from app.api.rack_rooms_api import ComisionBody, _ver, guardar_comisiones
from app.db import SessionLocal
from app.hotel_actual import HOTEL_ID
from app.models.canal_rooms import CanalSegmento
from app.models.rack_rooms import RackComision
from app.models.scenario import Scenario

MES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
       "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
D = lambda v: Decimal(str(v or 0))


async def main(nombre: str, pcts: list[str], aplicar: bool) -> int:
    async with SessionLocal() as db:
        escs = (await db.execute(select(Scenario).where(
            Scenario.hotel_id == HOTEL_ID))).scalars().all()
        cand = [s for s in escs
                if f"{s.type} {s.version} {s.year}".strip() == nombre]
        if len(cand) != 1:
            print(f"✗ Se buscaba un escenario «{nombre}» y hay {len(cand)}.")
            return 2
        esc = cand[0]
        print(f"escenario: {esc.type} {esc.version} {esc.year}")
        if esc.is_locked:
            print("✗ Enllavado. No se toca.")
            return 2

        # «13.6» o «0.136»: el owner copia de un cuadro con porcentajes.
        fracs = []
        for p in pcts:
            v = Decimal(str(p).replace("%", "").replace(",", ".").strip())
            if v > 1:
                v = v / Decimal("100")
            if not (Decimal("0") <= v < Decimal("1")):
                print(f"✗ «{p}» no es un descuento válido (0 a 100 %).")
                return 2
            fracs.append(v)

        segs = (await db.execute(select(CanalSegmento).where(
            CanalSegmento.hotel_id == HOTEL_ID,
            CanalSegmento.activo.is_(True)))).scalars().all()
        propias = {c.segmento_code for c in (await db.execute(select(
            RackComision).where(RackComision.scenario_id == esc.id,
                                RackComision.tarifa_propia.is_(True)))).scalars()}
        rack = [s for s in segs if s.genera_ingreso and s.code not in propias]
        print(f"segmentos que venden a rack: {len(rack)}   "
              f"(tarifa propia, sin tocar: {sorted(propias)})")

        antes = await _ver(db, esc.id)
        print(f"\n  antes:  neto {float(D(antes['total']['ingreso'])):>12,.2f}   "
              f"descuento {float(D(antes['total']['rack']['comision_pct']))*100:.2f}%")

        cuerpo = [ComisionBody(segmento_code=s.code, comision_pct=f,
                               tarifa_propia=False, month=i + 1)
                  for i, f in enumerate(fracs) for s in rack]
        if not aplicar:
            print(f"\nENSAYO: se escribirían {len(cuerpo)} filas "
                  f"({len(rack)} segmentos × 12 meses). Nada se guardó.")
            return 0

        await guardar_comisiones(esc.id, cuerpo, db, None)
        d = await _ver(db, esc.id)
        T, R = d["total"], d["total"]["rack"]
        print(f"\n  mes    desc.")
        for i, f in enumerate(fracs):
            print(f"  {MES[i]}   {float(f)*100:>5.1f}%")
        print(f"\n  ingreso rack       {float(D(R['ingreso_rack'])):>12,.2f}")
        print(f"  descuento          {float(D(R['comision_usd'])):>12,.2f}  "
              f"({float(D(R['comision_pct']))*100:.2f}%)")
        print(f"  INGRESO NETO       {float(D(T['ingreso'])):>12,.2f}")
        print(f"  ADR                {float(D(T['adr'])):>12,.2f}")
        return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--aplicar"]
    if len(args) != 13:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(
        main(args[0], args[1:], "--aplicar" in sys.argv)))
