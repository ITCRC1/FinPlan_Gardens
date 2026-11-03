# -*- coding: utf-8 -*-
"""UNA fila repetida congeló el mapeo entero durante dos meses.

## Qué pasó (encontrado el 2026-11-02, en producción)

`account_mapping` tiene DOS unicidades y no miran lo mismo:

    uq_account_mapping            (report_id, source_department, account_code,
                                   source_origin, vigente_desde)
    uq_mapping_activo_depto_cuenta(report_id, dept_code, account_code,
                                   vigente_desde, vigente_hasta)  WHERE activa

La clave de negocio del seed se deriva de la PRIMERA. La segunda —un índice
parcial que creó la migración 123— mira `dept_code` en vez de
`source_department`, y **no mira `source_origin`**.

El 2026-09-09 se le corrigió el `source_origin` a la regla del 7310 de Tours,
de `Revenue` a `Payroll`. Para el seed pasó a ser otra fila; para la base, la
misma. Entonces el seed la insertaba y Postgres la rechazaba.

`seed_mapping` confirma **una sola vez, al final de las dos siembras**. Ese
`IntegrityError` reventaba el `commit` y revertía el lote completo: las 1.150
reglas y las 123 líneas del reporte, en cada despliegue. El arranque lo
atrapaba, imprimía «seed de mapeo omitido: …» y seguía.

## Lo que costó

Las cuatro líneas de Rent (`REV_RENT`, `OPEX_RENT`, `COS_RENT`, `PROFIT_RENT`)
nunca llegaron a `report_line_config`. El alquiler de locales sumaba a
`TOTAL_REVENUES` —`SUM(REV_*)` lo tomaba de todos modos— pero no se dibujaba
en ninguna fila, porque el motor sólo emite las líneas que existen en la
configuración. Y **ningún cambio de mapeo se podía aplicar**: ni hacia
adelante, ni para revertir otro.

El total seguía cuadrando. Por eso duró dos meses.
"""
import pytest

from app.models.mapping import AccountMapping
from app.seed_mapping import (_COLS_INDICE_PARCIAL, _clave_mapeo,
                              _clave_ocupada_mapeo, _sembrar)

REGLA = {
    "active_status": "YES", "report_id": "P&L_DETAIL_OWNERS",
    "report_line_code": "OPEX_TOURS", "report_line_name": "Tours",
    "report_section": "OPERATING EXPENSES", "display_order": 39,
    "source_origin": "Payroll", "source_department": "Departamento de Tours",
    "account_code": "7310", "account_name_example": None,
    "financial_nature": "Expense", "rollup_operator": "SUM",
    "sign_rule": "x", "notes": None, "dept_code": "0150",
    "vigente_desde": None, "vigente_hasta": None,
}


class _Scalars:
    def __init__(self, objs): self._objs = objs
    def all(self): return self._objs


class _Result:
    def __init__(self, objs): self._objs = objs
    def scalars(self): return _Scalars(self._objs)


class _Sesion:
    """Lo mínimo que `_sembrar` usa: `execute(...).scalars().all()` y `add`."""
    def __init__(self, objs): self.objs = list(objs); self.agregadas = []
    async def execute(self, *a, **k): return _Result(self.objs)
    def add(self, o): self.agregadas.append(o)


def _en_la_base(**cambios):
    return AccountMapping(id="x", **{**REGLA, **cambios})


# ── La ranura del índice parcial ─────────────────────────────────────────────

def test_la_clave_alterna_es_la_del_indice_de_la_123():
    """Si el índice cambia y esto no, el seed vuelve a tumbarse solo."""
    assert _COLS_INDICE_PARCIAL == ("report_id", "dept_code", "account_code",
                                    "vigente_desde", "vigente_hasta")


def test_source_origin_no_entra_en_la_ranura():
    """Es la diferencia exacta que causó el choque: para la base, dos filas que
    sólo difieren en `source_origin` son LA MISMA."""
    a = _clave_ocupada_mapeo({**REGLA, "source_origin": "Revenue"})
    b = _clave_ocupada_mapeo({**REGLA, "source_origin": "Payroll"})
    assert a == b and a is not None
    # …y para la clave de negocio del seed son distintas. Ahí está el filo.
    assert _clave_mapeo({**REGLA, "source_origin": "Revenue"}) != _clave_mapeo(REGLA)


def test_una_regla_inactiva_no_ocupa_ranura():
    """El índice es PARCIAL (`WHERE active_status = 'YES'`). Tratar una
    inactiva como ocupante haría que el seed adoptara la fila equivocada —es
    el caso de la 8005, que existe activa e inactiva a la vez."""
    assert _clave_ocupada_mapeo({**REGLA, "active_status": "NO"}) is None


# ── El seed adopta en vez de insertar una gemela ─────────────────────────────

@pytest.mark.asyncio
async def test_adopta_la_fila_que_ya_ocupa_la_ranura():
    """El caso real del 7310: la base la tiene como `Revenue`, el archivo la
    trae como `Payroll`. Insertarla es un 23505 que revierte TODO el lote."""
    vieja = _en_la_base(source_origin="Revenue")
    sesion = _Sesion([vieja])

    await _sembrar(sesion, AccountMapping, [REGLA], _clave_mapeo,
                   "account_mapping", ocupada=_clave_ocupada_mapeo)

    assert sesion.agregadas == [], (
        "insertó una gemela: la base la rechaza y se cae la siembra entera")
    assert vieja.source_origin == "Payroll", "adoptó la fila pero no la corrigió"


@pytest.mark.asyncio
async def test_sin_la_clave_alterna_insertaria_la_gemela():
    """Deja a la vista que el arreglo es la clave alterna y no otra cosa."""
    sesion = _Sesion([_en_la_base(source_origin="Revenue")])
    await _sembrar(sesion, AccountMapping, [REGLA], _clave_mapeo,
                   "account_mapping")
    assert len(sesion.agregadas) == 1


@pytest.mark.asyncio
async def test_una_regla_de_verdad_nueva_si_se_inserta():
    """Adoptar no puede volverse 'nunca insertar': una cuenta que no existía
    tiene que entrar."""
    sesion = _Sesion([_en_la_base(source_origin="Revenue")])
    otra = {**REGLA, "account_code": "7311"}
    await _sembrar(sesion, AccountMapping, [REGLA, otra], _clave_mapeo,
                   "account_mapping", ocupada=_clave_ocupada_mapeo)
    assert [o.account_code for o in sesion.agregadas] == ["7311"]


@pytest.mark.asyncio
async def test_dos_filas_del_archivo_no_se_pisan_en_la_misma_ranura():
    """Si el ARCHIVO trajera dos filas para la misma ranura, la segunda no
    puede adoptar la recién insertada por la primera y perderse."""
    sesion = _Sesion([])
    a = {**REGLA, "source_origin": "Payroll"}
    b = {**REGLA, "source_origin": "Opex"}
    await _sembrar(sesion, AccountMapping, [a, b], _clave_mapeo,
                   "account_mapping", ocupada=_clave_ocupada_mapeo)
    # La primera entra; la segunda ADOPTA esa misma ranura en vez de insertar
    # una que la base rechazaría.
    assert len(sesion.agregadas) == 1
    assert sesion.agregadas[0].source_origin == "Opex"
