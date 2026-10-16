# -*- coding: utf-8 -*-
"""Los segmentos de venta de esta propiedad, desde su semilla.

Lee `seed_data/<HOTEL_ID>/canal_segmentos.json`. Una propiedad sin ese archivo
**no siembra nada**: heredar los segmentos de otra daría un mix ajeno y un
ingreso equivocado, que es el mismo razonamiento de `seed_canales_comerciales`.

## ⚠️ Agrega lo que falta; NO pisa lo que ya está

El seed corre en CADA deploy (`Procfile`). Re-afirmar campo por campo le
borraría al owner cualquier ajuste hecho desde la pantalla —un nombre, un
orden, un segmento desactivado— y lo haría en silencio, porque el total del
ingreso no cambia por eso.

Es la diferencia con `seed_mapping`, que sí manda sobre su tabla: allá el JSON
es la verdad y la base la copia; acá el JSON es el **arranque** y la base es la
verdad desde que alguien la toca.

⚠️ **Tampoco borra lo que sobra.** Un segmento que el owner agregó y no está en
el JSON se queda. Borrar por ausencia le vaciaría la grilla a una propiedad que
vende por un canal que nadie previó.
"""
from __future__ import annotations

import json
import pathlib

from sqlalchemy import select

from app.hotel_actual import HOTEL_ID
from app.models.canal_rooms import CanalSegmento

_SEED_DIR = pathlib.Path(__file__).parent / "seed_data"


def _archivo(hotel_id: str | None = None) -> pathlib.Path:
    return _SEED_DIR / (hotel_id or HOTEL_ID) / "canal_segmentos.json"


def leer(hotel_id: str | None = None) -> list[dict]:
    """La lista va bajo `"segmentos"`, como en `canales_comerciales.json`.

    El envoltorio no es decoración: deja lugar para el `_nota` que explica de
    dónde salieron los códigos, y hace que las dos semillas de la propiedad se
    lean igual. `app/estructura.py` cuenta las filas por esa misma llave.
    """
    f = _archivo(hotel_id)
    if not f.exists():
        return []
    return json.loads(f.read_text(encoding="utf-8")).get("segmentos", [])


async def seed_segmentos(db, hotel_id: str | None = None) -> dict:
    """Devuelve `{total, nuevos}`, o `{sin_semilla: True}` si no hay archivo."""
    hid = hotel_id or HOTEL_ID
    semilla = leer(hid)
    if not semilla:
        return {"total": 0, "nuevos": 0, "sin_semilla": True}

    actuales = {s.code for s in (await db.execute(
        select(CanalSegmento).where(CanalSegmento.hotel_id == hid))).scalars()}
    nuevos = 0
    for s in semilla:
        code = str(s["code"]).strip()
        if code in actuales:
            continue
        db.add(CanalSegmento(
            hotel_id=hid, code=code, nombre=s.get("nombre", code),
            # El default es `True`: un segmento nuevo FACTURA salvo que la
            # semilla diga lo contrario. Al revés, un canal recién agregado
            # quedaría fuera del ADR sin que nadie lo decidiera.
            genera_ingreso=bool(s.get("genera_ingreso", True)),
            orden=int(s.get("orden", 0)), activo=True))
        nuevos += 1
    await db.flush()
    return {"total": len(semilla), "nuevos": nuevos}
