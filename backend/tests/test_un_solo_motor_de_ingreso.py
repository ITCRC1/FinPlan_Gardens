# -*- coding: utf-8 -*-
"""El ingreso sale de UN cargador. La puerta del consolidado no tiene el suyo.

## Cómo apareció (2026-10-16)

El owner pidió construir el modelo de Rooms por RAC y avisó: *«debes hacer
tablas estándares porque después todo esto hay que consolidarlo en Hotel
Consolida»*. Antes de construir nada se midió esa puerta —
`GET /scenarios/{id}/revenue/monthly/`, que es la que Hotel Consolidation
consume— contra el motor del P&L, en producción:

    BUDGET Working 2026    API 0,00  vs  motor 397.039,20
    BUDGET Working 2027    API 0,00  vs  motor 295.455,98

El consolidado mostraba **Ojochal en cero** mientras el P&L mostraba $295 mil.

**Nada fallaba.** El total cuadraba consigo mismo, así que podía quedarse así
indefinidamente. La causa: `get_monthly_revenue` llamaba a
`calculate_annual_revenue`, que repite `calculate_revenue` mes a mes y **no
aplica ninguno de los drivers** que viven en `load_revenue_results`.

En Oxygen el mismo defecto escondía $1.107.238 (`MODELO_ROOMS_POR_CANAL.md` §7).

## El segundo defecto, en la misma puerta

`_revenue_result_to_dict` escribía **once** líneas de ingreso a mano cuando
`RevenueResult` ya tenía **catorce**: faltaban las tres del Club. Tampoco se
veía, porque `total_revenue` sí las sumaba —se calcula aparte—, así que el
cuadro cerraba contra un total que no era la suma de sus filas.

Es el mismo patrón que dejó al Club fuera del P&L cuando la lista de líneas
vivía escrita en el código. Por eso las dos pruebas de acá miran lo mismo desde
dos lados: que haya UN origen de verdad, y que nadie vuelva a escribir la lista.
"""
import inspect
import re

from app.api import revenue_api
from app.engine.recalculate import revenue_line_dict
from app.engine.revenue_calculator import RevenueResult


def _codigo(fn) -> str:
    """El CODIGO de la funcion, sin su docstring ni sus comentarios.

    Hace falta porque los docstrings de este repo NOMBRAN el defecto que
    previenen — es medio punto de su valor — y una prueba que busque el texto
    plano encuentra la explicacion y falla sobre la cura.
    """
    import ast as _ast
    import textwrap
    arbol = _ast.parse(textwrap.dedent(inspect.getsource(fn)))
    fn_ast = arbol.body[0]
    cuerpo = fn_ast.body[1:] if (fn_ast.body and isinstance(fn_ast.body[0], _ast.Expr)
                                 and isinstance(getattr(fn_ast.body[0], "value", None),
                                                _ast.Constant)
                                 and isinstance(fn_ast.body[0].value.value, str))         else fn_ast.body
    # `ast.unparse` tira los comentarios por su cuenta.
    return "\n".join(_ast.unparse(n) for n in cuerpo)


def _fuente_puerta() -> str:
    return _codigo(revenue_api.get_monthly_revenue)


def test_la_puerta_del_consolidado_usa_el_cargador_unico():
    """`load_revenue_results` y nada más."""
    f = _fuente_puerta()
    assert "load_revenue_results" in f, (
        "la puerta que lee Hotel Consolidation dejó de usar el cargador único"
    )


def test_la_puerta_no_tiene_su_propio_motor():
    """El defecto concreto: un segundo motor que no aplica los drivers."""
    f = _fuente_puerta()
    assert "calculate_annual_revenue" not in f, (
        "volvió el segundo motor a `get_monthly_revenue`. Esa función no aplica "
        "los drivers, así que el consolidado va a mostrar un número distinto al "
        "del P&L — y los dos van a cuadrar consigo mismos."
    )
    # `calculate_revenue` a secas tampoco: es el mismo camino sin drivers.
    assert not re.search(r"\bcalculate_revenue\s*\(", f), (
        "`calculate_revenue` llamado directo en la puerta: mismo defecto"
    )


def test_el_serializador_no_escribe_la_lista_de_lineas():
    """Las líneas se derivan de `revenue_line_dict`, que es el único lugar."""
    f = _codigo(revenue_api._revenue_result_to_dict)
    assert "revenue_line_dict" in f, (
        "el serializador volvió a escribir las líneas a mano: la próxima línea "
        "de ingreso que alguien agregue no va a llegar al consolidado"
    )
    # Ninguna línea de ingreso escrita suelta, con su nombre, en el diccionario.
    # `ast.unparse` normaliza las comillas a simples, así que se miran las dos
    # formas: la del archivo y la que devuelve `_codigo`.
    sueltas = [k for k in revenue_line_dict(RevenueResult(month=1, year=2027))
               if (f"'{k}': str(" in f or f'"{k}": str(' in f)]
    assert not sueltas, (
        f"líneas escritas a mano en el serializador: {sueltas}. Si una se "
        "olvida, el total la suma igual y el cuadro cierra contra un total que "
        "no es la suma de sus filas."
    )


def test_todas_las_lineas_del_motor_llegan_a_la_respuesta():
    """La prueba de verdad: ninguna línea se queda adentro.

    Se arma un `RevenueResult` con un valor DISTINTO en cada línea —y no con
    unos, que no distinguirían una línea pegada a otra— y se comprueba que
    todas salen.
    """
    r = RevenueResult(month=1, year=2027)
    esperado = {}
    for i, k in enumerate(revenue_line_dict(r), start=1):
        from decimal import Decimal
        v = Decimal(str(i * 1000 + i))      # 1001, 2002, 3003…
        setattr(r, k, v)
        esperado[k] = v

    d = revenue_api._revenue_result_to_dict(r)
    faltan = [k for k in esperado if k not in d]
    assert not faltan, f"líneas del motor que no llegan a la respuesta: {faltan}"

    malas = [k for k, v in esperado.items() if d[k] != str(v)]
    assert not malas, f"líneas que llegan con otro valor: {malas}"
