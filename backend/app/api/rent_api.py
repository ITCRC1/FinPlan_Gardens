# -*- coding: utf-8 -*-
"""Alquiler de locales — un contrato por fila, y su suma al P&L.

El owner alquila espacio dentro de la propiedad. Hoy son tres inquilinos en
Sabor; mañana pueden ser cinco. Por eso el detalle NO son líneas fijas del
checkbook sino filas de `rent_lines` que se crean y se apagan desde la pantalla.

**La suma de las filas activas es lo que el P&L ve**, y viaja por
`persistir_ingreso_de_driver` —el mismo camino del Spa y del Club—, que la deja
en las dos fuentes de ingreso. Si se guardara solo en `rent_lines`, la pantalla
mostraría la renta y el estado de resultados seguiría en cero: eso ya pasó una
vez y costó $125.180 (ver `app/api/_llega_al_pl.py`).

Un contrato que termina se APAGA, no se borra: los meses ya facturados siguen
explicándose. Apagado no suma.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._candado import candado
from app.api._ingreso_de_driver import persistir_ingreso_de_driver
from app.api._llega_al_pl import llega_al_pl, modo_ingresos
from app.db import get_db
from app.errores import ErrorApi
from app.models.mapping import AccountMapping
from app.models.rent_line import MESES, RentLine
from app.models.revenue_entry import REVENUE_LINE_ACCOUNT, REVENUE_LINE_LABELS
from app.models.scenario import Scenario
from app.textos import Idioma, t

router = APIRouter(tags=["rent"])

LINEA = "RENT"
DEPT_RENT, CUENTA_RENT = REVENUE_LINE_ACCOUNT[LINEA]
REPORTE = "P&L_DETAIL_OWNERS"


async def _cuentas(db: AsyncSession) -> list[dict]:
    """Las cuentas de alquiler que se pueden elegir, del catálogo.

    NO es una lista escrita en el código: sale de `account_mapping` (depto
    0157 → `REV_RENT`). Así, el día que hagan falta más locales, se agrega la
    regla en Admin → Account Mapping y aparece acá sola. El seed siembra
    4520-4535 — dieciséis — para que eso no haga falta por un buen rato.
    """
    filas = (await db.execute(
        select(AccountMapping).where(
            AccountMapping.report_id == REPORTE,
            AccountMapping.report_line_code == "REV_RENT",
            AccountMapping.dept_code == DEPT_RENT,
            AccountMapping.active_status == "YES",
        ).order_by(AccountMapping.account_code))).scalars()
    return [{"cuenta": f.account_code, "nombre": f.account_name_example or ""}
            for f in filas]


def _revisar_cuenta(cuenta: str, nombre: str, validas: set[str],
                    usadas: dict[str, str]) -> str:
    """Valida la cuenta de UN contrato y la anota. Devuelve la cuenta limpia.

    Vacía se permite: un contrato se firma antes de que contabilidad abra su
    cuenta, y mientras tanto la renta igual suma al P&L por la línea Rent — lo
    único que no se puede es cotejarla contra el mayor.
    """
    cuenta = (cuenta or "").strip()
    if not cuenta:
        return ""
    # Una cuenta inventada no la mapea nadie: el actual caería en otro renglón.
    if cuenta not in validas:
        raise ErrorApi(422, "rent.cuenta_desconocida", cuenta=cuenta, dept=DEPT_RENT)
    # Dos contratos en la misma cuenta dejan el P&L cuadrando y el detalle por
    # cuenta mezclado — justo lo que la cuenta venía a resolver.
    if cuenta in usadas:
        raise ErrorApi(422, "rent.cuenta_repetida", cuenta=cuenta,
                       nombre=usadas[cuenta])
    usadas[cuenta] = nombre
    return cuenta


async def _escenario(db: AsyncSession, scenario_id: str) -> Scenario:
    sc = await db.get(Scenario, scenario_id)
    if sc is None:
        raise ErrorApi(404, "escenario.no_encontrado")
    return sc


async def _filas(db: AsyncSession, scenario_id: str) -> list[RentLine]:
    return list((await db.execute(
        select(RentLine).where(RentLine.scenario_id == scenario_id)
        .order_by(RentLine.sort, RentLine.name))).scalars())


def _json(f: RentLine) -> dict:
    meses = [float(x) for x in f.meses()]
    return {"id": f.id, "name": f.name, "ubicacion": f.ubicacion or "",
            "cuenta": f.account_code or "", "notes": f.notes or "",
            "sort": f.sort, "active": bool(f.active),
            "meses": meses, "total": round(sum(meses), 2)}


def _total_mensual(filas: list[RentLine]) -> list[Decimal]:
    """Los doce montos que van al P&L. Las filas apagadas NO suman."""
    tot = [Decimal("0")] * 12
    for f in filas:
        if not f.active:
            continue
        for i, v in enumerate(f.meses()):
            tot[i] += v
    return tot


async def _persistir(db: AsyncSession, scenario: Scenario) -> None:
    filas = await _filas(db, scenario.id)
    await persistir_ingreso_de_driver(
        db, scenario, {LINEA: _total_mensual(filas)})


async def _respuesta(db: AsyncSession, scenario_id: str, idioma: str) -> dict:
    scenario = await _escenario(db, scenario_id)
    filas = await _filas(db, scenario_id)
    total = [float(x) for x in _total_mensual(filas)]
    cuentas = await _cuentas(db)
    tomada = {f.account_code: f.name for f in filas if f.account_code}
    return {
        "scenario_id": scenario_id, "year": scenario.year,
        "modo_ingresos": modo_ingresos(scenario),
        "llega_al_pl": llega_al_pl(scenario),
        "linea": {"linea": LINEA, "dept": DEPT_RENT, "cuenta": CUENTA_RENT,
                  "nombre": REVENUE_LINE_LABELS[LINEA]},
        # Cada cuenta dice si ya la tomó otro contrato: elegir una ocupada es
        # el error fácil, y verlo en la lista evita el viaje hasta el 422.
        "cuentas": [{**c, "tomada_por": tomada.get(c["cuenta"], "")} for c in cuentas],
        "filas": [_json(f) for f in filas],
        "total_mensual": [round(x, 2) for x in total],
        "total_anual": round(sum(total), 2),
        "nota": t(idioma, "rent.suma_al_pl"),
    }


@router.get("/scenarios/{scenario_id}/rent/")
async def leer(scenario_id: str, db: AsyncSession = Depends(get_db),
               idioma: str = Idioma):
    return await _respuesta(db, scenario_id, idioma)


class FilaIn(BaseModel):
    id: str | None = None
    name: str
    ubicacion: str = ""
    cuenta: str = ""
    notes: str = ""
    sort: int = 0
    active: bool = True
    meses: list[float] = []


class RentIn(BaseModel):
    filas: list[FilaIn]


@router.put("/scenarios/{scenario_id}/rent/")
async def guardar(scenario_id: str, body: RentIn,
                  db: AsyncSession = Depends(get_db), idioma: str = Idioma):
    """Guarda las filas que vienen y borra las que el usuario quitó.

    Se manda la lista COMPLETA, no un delta: así quitar una fila en pantalla y
    guardar no deja la vieja viva en la base. Lo que se quiere conservar pero ya
    no cobra va con `active: false`, que es distinto de quitarla.
    """
    scenario = await candado(db, scenario_id)
    vistos: set[str] = set()
    nombres: set[str] = set()
    cuentas_usadas: dict[str, str] = {}
    validas = {c["cuenta"] for c in await _cuentas(db)}
    existentes = {f.id: f for f in await _filas(db, scenario_id)}

    for orden, fin in enumerate(body.filas):
        nombre = (fin.name or "").strip()
        if not nombre:
            raise ErrorApi(422, "rent.nombre_vacio")
        if nombre.lower() in nombres:
            raise ErrorApi(422, "rent.nombre_repetido", nombre=nombre)
        nombres.add(nombre.lower())
        if len(fin.meses) not in (0, 12):
            raise ErrorApi(422, "rent.doce_meses")
        cuenta = _revisar_cuenta(fin.cuenta, nombre, validas, cuentas_usadas)

        fila = existentes.get(fin.id or "")
        if fila is None:
            fila = RentLine(scenario_id=scenario_id, hotel_id=scenario.hotel_id,
                            name=nombre)
            db.add(fila)
        fila.name = nombre
        fila.ubicacion = (fin.ubicacion or "").strip()
        fila.account_code = cuenta
        fila.notes = (fin.notes or "").strip()
        fila.sort = fin.sort if fin.sort else orden
        fila.active = bool(fin.active)
        for i, col in enumerate(MESES):
            if fin.meses:
                setattr(fila, col, Decimal(str(fin.meses[i] or 0)))
        vistos.add(fila.id)

    for fid, fila in existentes.items():
        if fid not in vistos:
            await db.delete(fila)
    await db.flush()

    await _persistir(db, scenario)
    await db.commit()
    return await _respuesta(db, scenario_id, idioma)
