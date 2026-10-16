# -*- coding: utf-8 -*-
"""Carga el tarifario RAC 2027 de Ojochal, del libro del owner.

Fuente: `Presupuesto_Ojochal_2027_Modelo 1_3 bismark.xlsx`, pestañas
`Origen Tarifa Rack` (pasos 1, 2 y 8) y `Resumen Manual` (las noches, columna
de la versión «Proyección 2027»).

## ⚠️ Escribe en UN escenario y en ninguno más

El escenario se nombra en la línea de comandos y se busca por nombre EXACTO.
En esta base conviven `BUDGET Working 2027` y `BUDGET Working-VIEJO 2027`, y
cargar en el equivocado no falla: deja los números en una versión que nadie
mira y el P&L del bueno sigue cuadrando consigo mismo.

## ⚠️ NO conecta el modelo

`scenarios.rooms_source` no se toca. Esto deja el tarifario cargado y listo
para mirar; enchufarlo al P&L es un acto del usuario, desde la pantalla.

## Verifica contra el libro ANTES de confirmar

Si el ingreso neto del año no da `402,091.65`, hace `rollback` y lo dice. El
punto de cargar esto es reproducir el libro: una carga que no lo reproduce no
es una carga a medias, es una carga equivocada.

Uso:
    python -m scripts.cargar_rack_2027 "BUDGET Working 2027"
    python -m scripts.cargar_rack_2027 "BUDGET Working 2027" --aplicar
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.db import SessionLocal
from app.engine.rack_tarifa import derivar_mes
from app.hotel_actual import HOTEL_ID
from app.models.canal_rooms import CanalRoomsEntry, CanalSegmento
from app.models.rack_rooms import RackComision, RackTemporada, RackVilla
from app.models.scenario import Scenario

ANIO = 2027

# ── Paso 1 del libro · unidades y RAC por villa ─────────────────────────────
VILLAS = [
    # villa,              unidades, pico, alta, verde
    ("Estudio Violeta",   3, "260", "220", "200"),
    ("Estudio Naranja",   3, "260", "220", "200"),
    ("Villa Amarilla",    1, "286", "240", "230"),
    ("Villa Verde",       1, "325", "280", "230"),
    ("Villa Fucsia",      1, "325", "280", "230"),
    ("Villa Turquesa",    1, "325", "280", "230"),
    ("Villa Azul",        1, "325", "280", "230"),
]

# ── Paso 2 · las temporadas. «Pico» son DOS rangos: enero y diciembre ───────
TEMPORADAS = [
    ("PICO",  date(2027, 1, 1),  date(2027, 1, 5)),
    ("ALTA",  date(2027, 1, 6),  date(2027, 4, 30)),
    ("VERDE", date(2027, 5, 1),  date(2027, 12, 19)),
    ("PICO",  date(2027, 12, 20), date(2027, 12, 31)),
]

# ── Paso 8 · la comisión implícita de cada segmento ─────────────────────────
#
# `CPL` no está: no factura, y el motor lo saca del ADR por `genera_ingreso`,
# no por una comisión del 100%.
COMISIONES = {
    "AGENCIAS":      ("0.25", False),
    "DIRECT_WEB":    ("0.10", False),
    "CRC_DIRECT":    ("0.25", False),
    "DIRECT_PHONE":  ("0.10", False),
    "DIRECT_GROUPS": ("0.15", False),
    "LONG_TERM":     ("0",    True),   # tarifa propia: no tiene RAC
    "OTA":           ("0.25", False),
}

# ── Paso 6 · las noches de la versión «Proyección 2027» ─────────────────────
NOCHES = {
    "AGENCIAS":      [25, 65, 45, 25, 20, 20, 50, 30, 20, 20, 20, 60],
    "DIRECT_WEB":    [150, 120, 150, 150, 100, 100, 70, 100, 10, 40, 60, 75],
    "CRC_DIRECT":    [8, 8, 10, 10, 6, 8, 8, 10, 6, 6, 8, 10],
    "DIRECT_PHONE":  [0, 30, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "DIRECT_GROUPS": [0] * 12,
    "LONG_TERM":     [30, 15, 0, 30, 30, 30, 30, 30, 30, 30, 30, 30],
    "OTA":           [25, 40, 40, 25, 20, 15, 25, 30, 15, 10, 10, 40],
    # En la Proyección 2027 no hay cortesías: el libro da 238 = 238 en enero
    # (filas 57 y 58 de `Resumen Manual`). Se carga explícito en CERO para que
    # la fila exista en la grilla y se pueda llenar sin crearla a mano.
    "CPL":           [0] * 12,
}

# ── Paso 6 · la tarifa propia de Long term, mes a mes ───────────────────────
LONG_TERM_TARIFA = ["75", "100", "0", "75", "75", "75", "75", "75",
                    "75", "75", "75", "75"]

# ── Lo que tiene que dar, según el libro ────────────────────────────────────
ESPERADO_NETO_ANIO = Decimal("402091.65")     # Origen Tarifa Rack · O85
ESPERADO_NETO_ENERO = Decimal("46958.75")     # Origen Tarifa Rack · C85
ESPERADO_DISPONIBLES = 4015                   # Origen Tarifa Rack · O48
ESPERADO_RAC_ENERO = Decimal("250.4692")      # Origen Tarifa Rack · C47
TOLERANCIA = Decimal("1.00")                  # el libro redondea al mostrar


async def main(nombre: str, aplicar: bool) -> int:
    async with SessionLocal() as db:
        escenarios = (await db.execute(select(Scenario).where(
            Scenario.hotel_id == HOTEL_ID,
            Scenario.year == ANIO))).scalars().all()
        candidatos = [s for s in escenarios
                      if f"{s.type} {s.version} {s.year}".strip() == nombre
                      or s.version == nombre]
        if len(candidatos) != 1:
            print(f"✗ Se buscaba exactamente un escenario llamado «{nombre}» y "
                  f"hay {len(candidatos)}. Los de {ANIO} son:")
            for s in escenarios:
                print(f"    {s.type} {s.version} {s.year}  id={s.id} "
                      f"{'🔒' if s.is_locked else ''}")
            return 2
        esc = candidatos[0]
        print(f"→ Escenario: {esc.type} {esc.version} {esc.year}  id={esc.id}")
        if esc.is_locked:
            print("✗ Está enllavado. No se toca.")
            return 2

        segs = {s.code: s for s in (await db.execute(select(CanalSegmento).where(
            CanalSegmento.hotel_id == HOTEL_ID))).scalars()}
        faltan = sorted(set(NOCHES) - set(segs))
        if faltan:
            print(f"✗ Faltan segmentos en el catálogo: {faltan}. "
                  f"Corré el seed (`python -m app.seed`) primero.")
            return 2

        # ── Villas ──────────────────────────────────────────────────────────
        for f in (await db.execute(select(RackVilla).where(
                RackVilla.scenario_id == esc.id))).scalars().all():
            await db.delete(f)
        await db.flush()
        for i, (villa, uds, pico, alta, verde) in enumerate(VILLAS):
            db.add(RackVilla(scenario_id=esc.id, hotel_id=HOTEL_ID, villa=villa,
                             unidades=uds, rac_pico=Decimal(pico),
                             rac_alta=Decimal(alta), rac_verde=Decimal(verde),
                             orden=i))

        # ── Temporadas ──────────────────────────────────────────────────────
        for f in (await db.execute(select(RackTemporada).where(
                RackTemporada.scenario_id == esc.id))).scalars().all():
            await db.delete(f)
        await db.flush()
        for temporada, desde, hasta in TEMPORADAS:
            db.add(RackTemporada(scenario_id=esc.id, hotel_id=HOTEL_ID,
                                 temporada=temporada, desde=desde, hasta=hasta))

        # ── Comisiones ──────────────────────────────────────────────────────
        actuales = {c.segmento_code: c for c in (await db.execute(
            select(RackComision).where(
                RackComision.scenario_id == esc.id))).scalars().all()}
        for code, (pct, propia) in COMISIONES.items():
            fila = actuales.get(code)
            if fila is None:
                fila = RackComision(scenario_id=esc.id, hotel_id=HOTEL_ID,
                                    segmento_code=code)
                db.add(fila)
            fila.comision_pct = Decimal(pct)
            fila.tarifa_propia = propia

        # ── Noches (y la tarifa propia de Long term) ────────────────────────
        existentes = {(f.segmento_code, f.month): f for f in (await db.execute(
            select(CanalRoomsEntry).where(
                CanalRoomsEntry.scenario_id == esc.id))).scalars().all()}
        for code, meses in NOCHES.items():
            for mes, noches in enumerate(meses, start=1):
                fila = existentes.get((code, mes))
                if fila is None:
                    fila = CanalRoomsEntry(scenario_id=esc.id, hotel_id=HOTEL_ID,
                                           segmento_code=code, month=mes)
                    db.add(fila)
                fila.noches = Decimal(str(noches))
                fila.tarifa_digitada = True
                if code == "LONG_TERM":
                    fila.tarifa = Decimal(LONG_TERM_TARIFA[mes - 1])
                fila.actualizado_por = "carga tarifario 2027"
        await db.flush()

        # ── Derivar, igual que lo hace la pantalla ───────────────────────────
        villas = (await db.execute(select(RackVilla).where(
            RackVilla.scenario_id == esc.id))).scalars().all()
        temps = (await db.execute(select(RackTemporada).where(
            RackTemporada.scenario_id == esc.id))).scalars().all()
        coms = {c.segmento_code: (c.comision_pct, bool(c.tarifa_propia))
                for c in (await db.execute(select(RackComision).where(
                    RackComision.scenario_id == esc.id))).scalars()}
        filas = (await db.execute(select(CanalRoomsEntry).where(
            CanalRoomsEntry.scenario_id == esc.id))).scalars().all()
        por_mes: dict[int, list] = {}
        for f in filas:
            por_mes.setdefault(int(f.month), []).append(f)

        neto_anio = Decimal("0")
        neto_enero = Decimal("0")
        rac_enero = Decimal("0")
        disponibles = 0
        for mes in range(1, 13):
            delmes = por_mes.get(mes, [])
            d = derivar_mes(villas, temps, coms,
                            {f.segmento_code: f.noches for f in delmes},
                            ANIO, mes,
                            tarifas_propias={f.segmento_code: f.tarifa
                                             for f in delmes})
            for f in delmes:
                s = d["segmentos"].get(f.segmento_code)
                if s:
                    f.tarifa, f.ingreso = s["tarifa"], s["ingreso"]
            mes_neto = sum((x["ingreso"] for x in d["segmentos"].values()),
                           Decimal("0"))
            neto_anio += mes_neto
            disponibles += d["disponibles"]
            if d["dias_sin_temporada"]:
                print(f"✗ Mes {mes}: {d['dias_sin_temporada']} días sin temporada.")
                await db.rollback()
                return 1
            if mes == 1:
                neto_enero, rac_enero = mes_neto, d["rac_ponderado"]

        # ── Contra el libro ─────────────────────────────────────────────────
        print(f"   RAC ponderado enero : {rac_enero:.4f}  "
              f"(libro {ESPERADO_RAC_ENERO})")
        print(f"   Noches disponibles  : {disponibles}  "
              f"(libro {ESPERADO_DISPONIBLES})")
        print(f"   Ingreso neto enero  : {neto_enero:,.2f}  "
              f"(libro {ESPERADO_NETO_ENERO:,.2f})")
        print(f"   Ingreso neto año    : {neto_anio:,.2f}  "
              f"(libro {ESPERADO_NETO_ANIO:,.2f})")

        problemas = []
        if disponibles != ESPERADO_DISPONIBLES:
            problemas.append("noches disponibles")
        if abs(rac_enero - ESPERADO_RAC_ENERO) > Decimal("0.001"):
            problemas.append("RAC de enero")
        if abs(neto_enero - ESPERADO_NETO_ENERO) > TOLERANCIA:
            problemas.append("ingreso neto de enero")
        if abs(neto_anio - ESPERADO_NETO_ANIO) > TOLERANCIA:
            problemas.append("ingreso neto del año")
        if problemas:
            print(f"✗ No reproduce el libro: {', '.join(problemas)}. "
                  f"Nada se guardó.")
            await db.rollback()
            return 1

        if not aplicar:
            print("✓ Reproduce el libro. ENSAYO: nada se guardó. "
                  "Volvé a correr con --aplicar.")
            await db.rollback()
            return 0

        await db.commit()
        print(f"✓ Guardado. `rooms_source` quedó en "
              f"«{getattr(esc, 'rooms_source', 'tarifas')}»: el modelo NO está "
              f"conectado al P&L todavía.")
        return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--aplicar"]
    if not args:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(args[0], "--aplicar" in sys.argv)))
