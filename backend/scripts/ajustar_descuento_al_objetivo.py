# -*- coding: utf-8 -*-
"""Sube (o baja) el descuento contra rack hasta dar un ingreso neto objetivo.

Owner, 2026-10-28: *«sube el descuento hasta llegar a 376 601»*.

## Cómo se resuelve

No hay que tantear: es una ecuación de una incógnita. El ingreso neto es

    neto = Σ rack_mes × (1 − desc_mes)  +  tarifa propia

y la tarifa propia (*Long term*) no lleva descuento, así que sale de los dos
lados. Queda despejar cuánto tienen que subir los `desc_mes`.

## Las dos formas de subirlos, y por qué importan

    proporcional   desc_mes × k     — conserva la FORMA del cuadro: el mes que
                                      tenía el doble de descuento lo sigue
                                      teniendo
    parejo         desc_mes + δ     — conserva la DISTANCIA: todos suben los
                                      mismos puntos

Dan tablas distintas y las dos llegan al mismo total. Cuál corresponde depende
de por qué suben los descuentos: si es que todo el año se negoció peor,
proporcional; si es un costo nuevo que pega igual en todos los meses, parejo.

⚠️ **La tarifa propia no se toca.** *Long term* no vende contra el tarifario:
si entrara en el ajuste, el objetivo se alcanzaría bajándole el ingreso a un
segmento que no tiene nada que ver con el descuento comercial.

Uso:
    python -m scripts.ajustar_descuento_al_objetivo "BUDGET Working 2027" 376601
    ... --proporcional --aplicar
    ... --parejo --aplicar
"""
from __future__ import annotations

import asyncio
import sys
from decimal import Decimal

from sqlalchemy import select

from app.api.rack_rooms_api import (ComisionBody, _cargar, _ver,
                                    comisiones_del_mes, guardar_comisiones)
from app.db import SessionLocal
from app.engine.rack_tarifa import rac_ponderado
from app.hotel_actual import HOTEL_ID
from app.models.canal_rooms import CanalRoomsEntry, CanalSegmento
from app.models.rack_rooms import RackComision
from app.models.scenario import Scenario

MES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
       "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
D = lambda v: Decimal(str(v or 0))
CENT = Decimal("0.01")


async def main(nombre: str, objetivo: Decimal, modo: str, aplicar: bool) -> int:
    async with SessionLocal() as db:
        escs = (await db.execute(select(Scenario).where(
            Scenario.hotel_id == HOTEL_ID))).scalars().all()
        cand = [s for s in escs
                if f"{s.type} {s.version} {s.year}".strip() == nombre]
        if len(cand) != 1:
            print(f"✗ Se buscaba un escenario «{nombre}» y hay {len(cand)}.")
            return 2
        esc = cand[0]
        if esc.is_locked:
            print("✗ Enllavado. No se toca.")
            return 2
        print(f"escenario: {esc.type} {esc.version} {esc.year}")

        villas, temps, coms = await _cargar(db, esc)
        propias = {c.segmento_code for c in coms if c.tarifa_propia}
        segs = (await db.execute(select(CanalSegmento).where(
            CanalSegmento.hotel_id == HOTEL_ID,
            CanalSegmento.activo.is_(True)))).scalars().all()
        genera = {s.code: bool(s.genera_ingreso) for s in segs}
        rack_segs = [s.code for s in segs
                     if s.genera_ingreso and s.code not in propias]

        filas = (await db.execute(select(CanalRoomsEntry).where(
            CanalRoomsEntry.scenario_id == esc.id))).scalars().all()

        # rack_mes = noches de los segmentos de rack × RAC ponderado del mes.
        # propio = lo que aportan los de tarifa propia, que no se toca.
        rack = {}
        propio = Decimal("0")
        for m in range(1, 13):
            r = rac_ponderado(villas, esc.year, m, temps)
            n = Decimal("0")
            for f in filas:
                if int(f.month) != m or not genera.get(f.segmento_code, True):
                    continue
                if f.segmento_code in propias:
                    propio += (D(f.noches) * D(f.tarifa)).quantize(CENT)
                else:
                    n += D(f.noches)
            rack[m] = (n * r).quantize(CENT)

        hoy = {m: D(comisiones_del_mes(coms, m).get(rack_segs[0], (0, False))[0])
               for m in range(1, 13)} if rack_segs else {}
        total_rack = sum(rack.values())
        pesado = sum(rack[m] * hoy.get(m, Decimal("0")) for m in range(1, 13))
        neto_hoy = total_rack - pesado + propio

        print(f"\n  ingreso rack (segmentos de rack)  {float(total_rack):>12,.2f}")
        print(f"  tarifa propia (no se toca)        {float(propio):>12,.2f}")
        print(f"  neto hoy                          {float(neto_hoy):>12,.2f}")
        print(f"  objetivo                          {float(objetivo):>12,.2f}")
        print(f"  falta                             {float(objetivo - neto_hoy):>+12,.2f}")

        # Lo que tiene que descontarse en total para dar el objetivo.
        necesario = total_rack + propio - objetivo
        if necesario < 0:
            print("\n✗ El objetivo es MAYOR que el ingreso a precio rack: "
                  "ningún descuento llega ahí. Habría que subir el RAC o las "
                  "noches.")
            return 1
        if necesario > total_rack:
            print("\n✗ El objetivo pide descontar más que todo el ingreso de "
                  "rack. Ni al 100 % de descuento se llega.")
            return 1

        # proporcional: desc × k      ·      parejo: desc + delta
        k = (necesario / pesado) if pesado else None
        delta = (necesario - pesado) / total_rack if total_rack else None

        print("\n  mes    hoy    proporcional    parejo")
        print("  " + "-" * 42)
        prop, par = {}, {}
        for m in range(1, 13):
            d0 = hoy.get(m, Decimal("0"))
            p1 = (d0 * k) if k is not None else d0
            p2 = d0 + delta
            prop[m], par[m] = p1, p2
            print(f"  {MES[m-1]}  {float(d0)*100:>5.1f}%     "
                  f"{float(p1)*100:>6.2f}%     {float(p2)*100:>6.2f}%")
        print("  " + "-" * 42)
        if k is not None:
            print(f"  factor proporcional: ×{float(k):.5f}")
        print(f"  puntos a sumar     : +{float(delta)*100:.3f} pp")

        malos = [MES[m-1] for m in range(1, 13)
                 if not (Decimal("0") <= (prop[m] if modo == "proporcional" else par[m]) < Decimal("1"))]
        if malos:
            print(f"\n✗ Con «{modo}» estos meses quedan fuera de 0-100 %: {malos}")
            return 1

        elegido = prop if modo == "proporcional" else par
        comprobacion = sum(rack[m] * (Decimal("1") - elegido[m])
                           for m in range(1, 13)) + propio
        print(f"\n  con «{modo}» el neto da {float(comprobacion):,.2f}  "
              f"(objetivo {float(objetivo):,.2f})")

        if not aplicar:
            print("\nENSAYO: nada se guardó. Agregá --aplicar y el modo.")
            return 0

        cuerpo = [ComisionBody(segmento_code=c,
                               comision_pct=elegido[m].quantize(Decimal("0.0001")),
                               tarifa_propia=False, month=m)
                  for m in range(1, 13) for c in rack_segs]
        await guardar_comisiones(esc.id, cuerpo, db, None)
        d = await _ver(db, esc.id)
        T, R = d["total"], d["total"]["rack"]
        print(f"\n✓ Guardado ({modo}).")
        print(f"  ingreso rack   {float(D(R['ingreso_rack'])):>12,.2f}")
        print(f"  descuento      {float(D(R['comision_usd'])):>12,.2f}  "
              f"({float(D(R['comision_pct']))*100:.2f}%)")
        print(f"  INGRESO NETO   {float(D(T['ingreso'])):>12,.2f}")
        print(f"  ADR            {float(D(T['adr'])):>12,.2f}")
        return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        print(__doc__)
        raise SystemExit(2)
    modo = "parejo" if "--parejo" in sys.argv else "proporcional"
    raise SystemExit(asyncio.run(main(
        args[0], Decimal(args[1].replace(",", "").replace("$", "")),
        modo, "--aplicar" in sys.argv)))
