# -*- coding: utf-8 -*-
"""El alquiler de locales llega al P&L, y llega a SU renglón.

Dos cosas distintas que conviene no mezclar:

1. **Que llegue.** La pantalla guarda contratos en `rent_lines`, pero el P&L no
   lee esa tabla: lee las líneas de ingreso. Si la suma no se depositara ahí, la
   pantalla mostraría la renta y el estado de resultados seguiría en cero —el
   mismo agujero que le costó $125.180 al Club (ver `_llega_al_pl.py`).

2. **Que llegue aparte.** Los inquilinos ocupan espacio DENTRO de Sabor Ojochal
   y por eso su renta venía cayendo en las cuentas del 0155. Si `RENT` quedara
   apuntando al grupo de Sabor, el owner volvería a ver la renta sumada a lo que
   Sabor factura por su operación, que es justo lo que pidió separar.
"""
import json
import pathlib
from decimal import Decimal

import pytest

from app.api.rent_api import _agrupar, _revisar_cuenta, _total_mensual
from app.errores import ErrorApi
from app.engine import pl_engine as pe
from app.models.rent_line import RentLine
from app.models.revenue_entry import (REVENUE_LINE_ACCOUNT, REVENUE_LINE_LABELS,
                                      REVENUE_LINES)

ARCHIVO = pathlib.Path(__file__).resolve().parents[1] / "app/seed_data/mapping_pl.json"
#: Las que siembra el seed para el depto 0157.
VALIDAS = {str(c) for c in range(4520, 4536)}


def _fila(nombre, monto, active=True, concepto="Alquiler", cuenta="", sort=0):
    f = RentLine(name=nombre, active=active, concepto=concepto,
                 account_code=cuenta, sort=sort, ubicacion="", notes="")
    for m in range(1, 13):
        f.set_month(m, Decimal(str(monto)))
    return f


def test_la_suma_de_los_contratos_activos_es_la_que_viaja():
    filas = [_fila("Apotecaria Botánica", 500),
             _fila("Momento Wine Paradise", 300),
             _fila("XFIT-ORC", 200)]
    assert _total_mensual(filas) == [Decimal("1000")] * 12


def test_un_contrato_apagado_no_suma():
    """Apagar no es borrar: la fila sigue, su plata no."""
    filas = [_fila("Apotecaria Botánica", 500),
             _fila("Local que cerró", 400, active=False)]
    assert _total_mensual(filas) == [Decimal("500")] * 12


def test_rent_es_una_linea_de_ingreso_con_su_cuenta():
    assert "RENT" in REVENUE_LINES
    assert REVENUE_LINE_LABELS["RENT"] == "Rent"
    dept, cuenta = REVENUE_LINE_ACCOUNT["RENT"]
    assert dept == "0157", "el alquiler tiene departamento propio"
    assert cuenta == "4520", "y rango de cuenta propio, no el 4500 de Sabor"


def test_el_alquiler_no_cae_en_sabor_ojochal():
    """La trampa que esta prueba cuida: el local está adentro de Sabor."""
    assert pe.REVENUE_LINE_TO_GROUP["rent"] == "RENT"
    assert pe.REVENUE_LINE_TO_GROUP["innoceana"] == "SABOR_OJOCHAL"
    assert pe.REVENUE_LINE_TO_REPORT_LINE["rent"] == "REV_RENT"
    assert pe.OPERATING_DEPT_GROUPS["RENT"] == ["0157"]
    assert "0157" not in pe.OPERATING_DEPT_GROUPS["SABOR_OJOCHAL"]


def test_el_grupo_rent_se_dibuja_y_tiene_nombre():
    assert "RENT" in pe.OPERATING_GROUP_ORDER
    assert pe.GROUP_NAMES["RENT"] == "Rent"
    assert pe.GROUP_TO_REVENUE_LINE["RENT"] == "rent"


def test_el_seed_trae_las_cuatro_lineas_del_pl():
    """Sin estas cuatro filas el motor calcula el grupo y el reporte no lo dibuja."""
    d = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    codigos = {r["line_code"] for r in d["report_line_config"]}
    for c in ("REV_RENT", "OPEX_RENT", "COS_RENT", "PROFIT_RENT"):
        assert c in codigos, f"falta {c} en report_line_config"
    profit = next(r for r in d["report_line_config"] if r["line_code"] == "PROFIT_RENT")
    assert profit["calculation_logic"] == "REV_RENT - OPEX_RENT - COS_RENT"


def test_el_seed_mapea_el_0157_y_no_le_roba_cuentas_a_nadie():
    d = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    am = d["account_mapping"]
    mias = [r for r in am if r.get("dept_code") == "0157"]
    assert mias, "el 0157 no tiene una sola regla: su gasto caería en Habitaciones"
    assert {r["report_line_code"] for r in mias} == {"REV_RENT", "OPEX_RENT", "COS_RENT"}
    # Dieciséis cuentas: hoy se alquilan tres locales y el rango deja aire para
    # que agregar un inquilino sea elegir una cuenta libre, no tocar código.
    ingreso = sorted(r["account_code"] for r in mias
                     if r["report_line_code"] == "REV_RENT")
    assert ingreso == [str(c) for c in range(4520, 4536)]
    # La llave de negocio es (report_id, depto, cuenta, origen). Dos reglas con
    # la misma llave se insertarían como una sola y la otra se perdería.
    llaves = [(r["report_id"], r["source_department"], r["account_code"],
               r["source_origin"]) for r in am]
    assert len(llaves) == len(set(llaves)), "hay reglas con la llave repetida"


def test_el_0157_esta_en_el_catalogo_de_departamentos():
    from app.seed_department_catalog import DEPT_NAMES
    assert DEPT_NAMES["0157"] == "Rent"


def test_dos_contratos_no_pueden_compartir_cuenta():
    """El P&L cuadraría igual; el detalle por cuenta quedaría mezclado y no
    habría forma de cotejar el mayor inquilino por inquilino."""
    usadas: dict[str, str] = {}
    assert _revisar_cuenta("4520", "Apotecaria Botánica", VALIDAS, usadas) == "4520"
    with pytest.raises(ErrorApi) as e:
        _revisar_cuenta("4520", "XFIT-ORC", VALIDAS, usadas)
    assert e.value.status_code == 422


def test_una_cuenta_que_no_es_de_alquiler_se_rechaza():
    """4500 es de Sabor Ojochal y del Club. Aceptarla mandaría el actual del
    alquiler al renglón de otro departamento, con el total cuadrando."""
    with pytest.raises(ErrorApi) as e:
        _revisar_cuenta("4500", "Momento Wine Paradise", VALIDAS, {})
    assert e.value.status_code == 422


def test_un_contrato_sin_cuenta_se_acepta():
    """Se firma antes de que contabilidad abra la cuenta. La renta igual suma."""
    usadas: dict[str, str] = {}
    assert _revisar_cuenta("", "Local recién firmado", VALIDAS, usadas) == ""
    assert usadas == {}


def test_un_inquilino_son_varias_filas_y_se_agrupan():
    """«No quiero solo una cuenta, quiero un set de cuentas» (owner, 2026-11-01).
    Un local paga alquiler, mantenimiento y servicios: tres cuentas, un solo
    inquilino. En la base viven planas; la pantalla ve el contrato entero."""
    filas = [_fila("Apotecaria Botánica", 500, concepto="Alquiler", cuenta="4520"),
             _fila("Apotecaria Botánica", 80, concepto="Mantenimiento", cuenta="4521"),
             _fila("Apotecaria Botánica", 40, concepto="Servicios", cuenta="4522"),
             _fila("XFIT-ORC", 300, concepto="Alquiler", cuenta="4523", sort=1)]
    contratos = _agrupar(filas)
    assert [c["name"] for c in contratos] == ["Apotecaria Botánica", "XFIT-ORC"]
    apo = contratos[0]
    assert [i["concepto"] for i in apo["items"]] == ["Alquiler", "Mantenimiento", "Servicios"]
    assert [i["cuenta"] for i in apo["items"]] == ["4520", "4521", "4522"]
    # el contrato suma sus conceptos, mes a mes
    assert apo["total_mensual"] == [620.0] * 12
    assert apo["total"] == 7440.0


def test_el_pl_ve_todos_los_conceptos_no_solo_el_alquiler():
    """Si el P&L leyera solo la fila «Alquiler», el mantenimiento y los
    servicios se cobrarían y no aparecerían en ningún lado."""
    filas = [_fila("Apotecaria Botánica", 500, concepto="Alquiler"),
             _fila("Apotecaria Botánica", 80, concepto="Mantenimiento"),
             _fila("XFIT-ORC", 300, concepto="Alquiler")]
    assert _total_mensual(filas) == [Decimal("880")] * 12


def test_apagar_el_contrato_apaga_todos_sus_conceptos():
    """El interruptor es del inquilino: si se fue, no cobra ninguno de sus
    conceptos. Apagar uno por uno dejaría un cobro suelto sin que nadie lo vea."""
    filas = [_fila("Local que cerró", 500, active=False, concepto="Alquiler"),
             _fila("Local que cerró", 80, active=False, concepto="Mantenimiento"),
             _fila("XFIT-ORC", 300, concepto="Alquiler")]
    assert _total_mensual(filas) == [Decimal("300")] * 12
