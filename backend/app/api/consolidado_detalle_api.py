# -*- coding: utf-8 -*-
"""Posiciones, planilla y checkbook de OPEX, por API, para el Excel en vivo.

Owner, 2026-11-11: *«mete un P&L usali, posiciones y checkbook de gastos y
planilla»* — en el mismo libro que ya baja el GL por mes con refresh.

**Por qué va en un módulo aparte y no en `consolidado_api`.** Aquel es el
contrato ENTRE propiedades: totales por línea y nada más, y una prueba exige que
no toque planilla ni OPEX (`test_el_consolidado_no_expone_detalle`). Esto es otra
cosa: el detalle de UNA propiedad, pedido por su owner, para su libro. Meterlo
allá habría obligado a borrar esa prueba, y la regla sigue valiendo para lo que
consume Hotel Consolidation.

**Misma puerta** (`lector_del_consolidado`: la llave de solo lectura o una
sesión) y **mismo criterio para escoger el escenario** que el GL en vivo
(`_escoger_escenario`): año + tipo + versión por nombre, el ★ Current del
forecast cuando no se dice versión.

**Lo que NO sale, a propósito: el nombre de la persona.** Una posición se
identifica por su código y su puesto; quién la ocupa no hace falta para
presupuestar y es lo primero que no tiene que viajar en un archivo que se
reenvía. El salario sí sale: sin él no hay checkbook de planilla.

**Se reusa el armado de la pantalla.** Posiciones y planilla salen de
`planilla_por_posicion` (el reporte «Planilla por posición»), así que lo que baja
el libro es lo que muestra el sistema, concepto por concepto.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api._nombres_de_depto import nombres_de_depto
from app.api.consolidado_api import CONTRATO, TIPOS, _escoger_escenario
from app.auth import lector_del_consolidado
from app.db import get_session
from app.errores import ErrorApi
from app.hotel_actual import HOTEL_ID, HOTEL_NAME
from app.models.opex_entry import OpexEntry
from app.models.scenario import Scenario

router = APIRouter()


async def _escenario(session, year: int, tipo: str, version: str | None) -> Scenario:
    tipo = tipo.upper()
    if tipo not in TIPOS:
        raise ErrorApi(422, "consolidado.tipo_invalido", tipos=", ".join(TIPOS))
    escenarios = (await session.execute(
        select(Scenario).where(Scenario.hotel_id == HOTEL_ID, Scenario.year == year,
                               Scenario.type == tipo)
        .order_by(Scenario.created_at.desc()))).scalars().all()
    escenario = _escoger_escenario(list(escenarios), tipo, version)
    if escenario is None:
        if version:
            raise ErrorApi(404, "consolidado.sin_escenario_version",
                           propiedad=HOTEL_NAME, tipo=tipo, version=version, anio=year)
        raise ErrorApi(404, "consolidado.sin_escenario", propiedad=HOTEL_NAME, tipo=tipo, anio=year)
    return escenario


def _cabecera(year: int, tipo: str, escenario: Scenario) -> dict:
    return {
        "contrato": CONTRATO,
        "hotel_id": HOTEL_ID,
        "hotel_name": HOTEL_NAME,
        "year": year,
        "tipo": tipo.upper(),
        "escenario": {
            "id": escenario.id, "version": escenario.version, "status": escenario.status,
            "actuals_through": getattr(escenario, "actuals_through", None) or 0,
        },
        "moneda": "USD",
    }


@router.get("/consolidado/posiciones/")
async def consolidado_posiciones(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST · ACTUAL"),
    version: str | None = Query(None, description="Versión exacta; por defecto ★ Current (forecast) o el real"),
    quien: str = Depends(lector_del_consolidado),
):
    """Las posiciones de planilla con su FTE por mes y sus 17 conceptos por mes.

    Una respuesta sirve a las dos hojas del libro: «Posiciones» (una fila por
    posición) y «Planilla» (posición × concepto × mes). En un escenario de
    actuales las filas con código `GL` son la planilla real del mayor, una por
    departamento, sin persona detrás.
    """
    from app.api.payroll_position_report_api import planilla_por_posicion

    async with get_session() as session:
        escenario = await _escenario(session, year, tipo, version)
        rep = await planilla_por_posicion(scenario_id=escenario.id, dept="", db=session)

    return {
        **_cabecera(year, tipo, escenario),
        "conceptos": rep["conceptos"],
        "posiciones": [{
            "codigo": f["position_code"],
            "puesto": f["position_name"],
            "dept": f["dept_code"],
            "dept_name": f["dept_name"],
            "moneda_salario": f["salary_currency"],
            "salario": f["salary_amount"],
            "fte": f["fte"],
            "fte_prom": f["fte_prom"],
            "devengado": f["devengado"],
            "cargas": f["cargas"],
            "beneficios": f["beneficios"],
            "costo": f["costo"],
            # {columna: [12 meses]} en USD, con la clave de concepto de arriba.
            "meses": f["meses"],
            # Lo que se deja afuera: `employee_name`. Ver el docstring del módulo.
        } for f in rep["rows"]],
        "total_costo": rep["totales"]["costo"],
    }


@router.get("/consolidado/opex/")
async def consolidado_opex(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST · ACTUAL"),
    version: str | None = Query(None, description="Versión exacta; por defecto ★ Current (forecast) o el real"),
    quien: str = Depends(lector_del_consolidado),
):
    """El checkbook de OPEX (clase 7): una fila por depto × cuenta × detalle.

    Son las líneas que se digitan en «OPEX por departamento», en USD (si la
    línea es en colones, los dólares son los derivados con el TC de cada mes, y
    los colones del año vienen aparte). No incluye lo que le cae a un
    departamento por reparto: eso no es una línea del checkbook. En un
    escenario de actuales el gasto real vive en el GL, no acá.
    """
    async with get_session() as session:
        escenario = await _escenario(session, year, tipo, version)
        nombres = await nombres_de_depto(session)
        lineas = (await session.execute(
            select(OpexEntry).where(OpexEntry.scenario_id == escenario.id)
            .order_by(OpexEntry.dept_code, OpexEntry.account_code, OpexEntry.detail_code)
        )).scalars().all()

    return {
        **_cabecera(year, tipo, escenario),
        "lineas": [{
            "dept": e.dept_code,
            "dept_name": nombres.get(e.dept_code, ""),
            "cuenta": e.account_code,
            "nombre": e.account_name,
            "detalle": e.detail_code,
            "detalle_desc": e.detail_desc,
            "moneda": e.currency or "USD",
            "meses": [float(e.get_month(m) or 0) for m in range(1, 13)],
            "anual": float(sum((e.get_month(m) or 0) for m in range(1, 13))),
            "crc_anual": float(sum(e.get_crc(m) for m in range(1, 13))) if e.en_colones else 0.0,
        } for e in lineas],
    }
